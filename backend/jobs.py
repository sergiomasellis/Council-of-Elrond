"""Job management for durable streaming responses."""

import asyncio
import json
import uuid
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import storage
from .council import (
    stage1_collect_responses_stream,
    stage2_collect_rankings_stream,
    stage3_synthesize_final_stream,
    parse_ranking_from_text,
    calculate_aggregate_rankings,
    generate_conversation_title,
)


@dataclass
class Job:
    """Represents an in-flight council pipeline job."""
    job_id: str
    conversation_id: str
    query: str
    status: str = "pending"  # pending -> stage1 -> stage2 -> stage3 -> complete | error
    events: list = field(default_factory=list)
    new_event: asyncio.Event = field(default_factory=asyncio.Event)
    stage1_results: Optional[List[Dict[str, Any]]] = None
    stage2_results: Optional[List[Dict[str, Any]]] = None
    stage3_result: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    task: Optional[asyncio.Task] = None


class JobManager:
    """In-memory registry of active jobs, keyed by conversation_id."""

    def __init__(self):
        self._jobs: Dict[str, Job] = {}  # job_id -> Job
        self._by_conversation: Dict[str, str] = {}  # conversation_id -> job_id

    def create_job(self, conversation_id: str, query: str) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, conversation_id=conversation_id, query=query)
        self._jobs[job_id] = job
        self._by_conversation[conversation_id] = job_id
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def get_active_job(self, conversation_id: str) -> Optional[Job]:
        job_id = self._by_conversation.get(conversation_id)
        if job_id is None:
            return None
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in ("complete", "error"):
            return None
        return job

    def get_any_job(self, conversation_id: str) -> Optional[Job]:
        """Get the most recent job for a conversation, regardless of status."""
        job_id = self._by_conversation.get(conversation_id)
        if job_id is None:
            return None
        return self._jobs.get(job_id)

    def append_event(self, job: Job, event: dict):
        job.events.append(event)
        # Wake all listeners, then replace with a fresh Event
        job.new_event.set()
        job.new_event = asyncio.Event()

    def cleanup_old_jobs(self, max_age_seconds: int = 3600):
        now = time.time()
        to_delete = [
            jid for jid, job in self._jobs.items()
            if job.status in ("complete", "error") and (now - job.created_at) > max_age_seconds
        ]
        for jid in to_delete:
            job = self._jobs.pop(jid, None)
            if job:
                self._by_conversation.pop(job.conversation_id, None)


# Singleton
job_manager = JobManager()


def _save_partial_assistant(conversation_id: str, job: Job):
    """Progressively save assistant message to storage."""
    storage.upsert_assistant_message(
        conversation_id,
        job_id=job.job_id,
        status=job.status,
        stage1=job.stage1_results,
        stage2=job.stage2_results,
        stage3=job.stage3_result,
        metadata=job.metadata,
    )


async def run_council_pipeline(job: Job):
    """Run the 3-stage council pipeline, emitting events to the job."""
    conversation_id = job.conversation_id
    query = job.query

    try:
        # Load conversation history for multi-turn context
        conversation = storage.get_conversation(conversation_id)
        prior_messages = conversation["messages"][:-1] if conversation and len(conversation["messages"]) > 1 else []
        conversation_history = prior_messages if prior_messages else None

        # --- Stage 1 ---
        job.status = "stage1"
        job_manager.append_event(job, {"type": "stage1_start"})

        stage1_results_map: Dict[str, str] = {}

        async for model, chunk in stage1_collect_responses_stream(query, conversation_history):
            if model not in stage1_results_map:
                stage1_results_map[model] = ""
                job_manager.append_event(job, {
                    "type": "stage1_init",
                    "data": {"model": model, "response": ""},
                })

            stage1_results_map[model] += chunk
            job_manager.append_event(job, {
                "type": "stage1_chunk",
                "model": model,
                "chunk": chunk,
            })

        stage1_results = [
            {"model": model, "response": response}
            for model, response in stage1_results_map.items()
        ]
        job.stage1_results = stage1_results

        job_manager.append_event(job, {
            "type": "stage1_complete",
            "data": stage1_results,
        })

        # Save after stage 1
        _save_partial_assistant(conversation_id, job)

        # --- Stage 2 ---
        job.status = "stage2"
        job_manager.append_event(job, {"type": "stage2_start"})

        stage2_results_map: Dict[str, str] = {}
        label_to_model = {}

        async for model, chunk, ltm in stage2_collect_rankings_stream(query, stage1_results):
            if ltm is not None:
                label_to_model = ltm
                job_manager.append_event(job, {
                    "type": "stage2_map",
                    "data": label_to_model,
                })
                continue

            if model not in stage2_results_map:
                stage2_results_map[model] = ""
                job_manager.append_event(job, {
                    "type": "stage2_init",
                    "data": {"model": model, "ranking": ""},
                })

            stage2_results_map[model] += chunk
            job_manager.append_event(job, {
                "type": "stage2_chunk",
                "model": model,
                "chunk": chunk,
            })

        stage2_results = []
        for model, ranking_text in stage2_results_map.items():
            parsed = parse_ranking_from_text(ranking_text)
            stage2_results.append({
                "model": model,
                "ranking": ranking_text,
                "parsed_ranking": parsed,
            })

        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        job.stage2_results = stage2_results
        job.metadata = {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings,
        }

        job_manager.append_event(job, {
            "type": "stage2_complete",
            "data": stage2_results,
            "metadata": job.metadata,
        })

        # Save after stage 2
        _save_partial_assistant(conversation_id, job)

        # --- Stage 3 ---
        job.status = "stage3"
        job_manager.append_event(job, {"type": "stage3_start"})

        stage3_model = ""
        stage3_full_response = ""

        async for event in stage3_synthesize_final_stream(query, stage1_results, stage2_results, conversation_history):
            if event["type"] == "model_info":
                stage3_model = event["model"]
                job_manager.append_event(job, {
                    "type": "stage3_init",
                    "data": {"model": stage3_model, "response": ""},
                })
            elif event["type"] == "content_chunk":
                chunk = event["chunk"]
                stage3_full_response += chunk
                job_manager.append_event(job, {
                    "type": "stage3_chunk",
                    "chunk": chunk,
                })
            elif event["type"] == "complete":
                job.stage3_result = event["data"]

        job_manager.append_event(job, {
            "type": "stage3_complete",
            "data": job.stage3_result,
        })

        # --- Title generation (if first message) ---
        conversation = storage.get_conversation(conversation_id)
        if conversation and len(conversation["messages"]) <= 2:
            # First user + first assistant = 2 messages
            try:
                title = await generate_conversation_title(query)
                storage.update_conversation_title(conversation_id, title)
                job_manager.append_event(job, {
                    "type": "title_complete",
                    "data": {"title": title},
                })
            except Exception:
                pass  # Title generation is best-effort

        # --- Complete ---
        job.status = "complete"
        _save_partial_assistant(conversation_id, job)
        job_manager.append_event(job, {"type": "complete"})

    except Exception as e:
        traceback.print_exc()
        job.status = "error"
        _save_partial_assistant(conversation_id, job)
        job_manager.append_event(job, {
            "type": "error",
            "message": str(e),
        })
