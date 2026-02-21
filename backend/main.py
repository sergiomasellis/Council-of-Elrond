"""FastAPI backend for LLM Council."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import json
import asyncio

from . import storage
from .council import run_full_council, generate_conversation_title
from .jobs import job_manager, run_council_pipeline


# --- Lifecycle ---

async def _periodic_cleanup():
    """Remove completed jobs older than 1 hour, every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        job_manager.cleanup_old_jobs()


async def _mark_orphaned_messages():
    """On startup, mark any in-progress assistant messages as 'error'."""
    try:
        conversations = storage.list_conversations()
        for conv_meta in conversations:
            conv = storage.get_conversation(conv_meta["id"])
            if conv is None:
                continue
            changed = False
            for msg in conv["messages"]:
                if msg.get("role") == "assistant" and msg.get("status") not in (None, "complete", "error"):
                    msg["status"] = "error"
                    changed = True
            if changed:
                storage.save_conversation(conv)
    except Exception:
        pass  # Best-effort on startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await _mark_orphaned_messages()
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="LLM Council API", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "success", "id": conversation_id}


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0

    storage.add_user_message(conversation_id, request.content)

    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


# --- Streaming with durable jobs ---

async def _stream_job_events(job, start_index: int = 0):
    """
    SSE generator that drains buffered events then goes live.

    Supports multiple concurrent readers on the same job.
    """
    idx = start_index

    while True:
        # Drain any buffered events
        while idx < len(job.events):
            event = job.events[idx]
            idx += 1
            yield f"data: {json.dumps(event)}\n\n"
            # Stop after terminal event
            if event.get("type") in ("complete", "error"):
                return

        # If job is already terminal and we've caught up, stop
        if job.status in ("complete", "error"):
            return

        # Wait for new events with a timeout for keepalive
        waiter = job.new_event
        try:
            await asyncio.wait_for(asyncio.shield(waiter.wait()), timeout=30.0)
        except asyncio.TimeoutError:
            # Send keepalive comment
            yield ": keepalive\n\n"


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process via SSE.
    Spawns a background task so the pipeline survives client disconnects.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Reject if there's already an active job for this conversation
    existing = job_manager.get_active_job(conversation_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A job is already running for this conversation",
            headers={"X-Job-Id": existing.job_id},
        )

    # Add user message to storage
    storage.add_user_message(conversation_id, request.content)

    # Create and start job (title generation is handled inside the pipeline)
    job = job_manager.create_job(conversation_id, request.content)
    job.task = asyncio.create_task(run_council_pipeline(job))

    return StreamingResponse(
        _stream_job_events(job, start_index=0),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Job-Id": job.job_id,
        },
    )


@app.get("/api/conversations/{conversation_id}/job/status")
async def get_job_status(conversation_id: str):
    """Check if there's an active job for this conversation."""
    job = job_manager.get_active_job(conversation_id)
    if job is None:
        return {"active": False}
    return {
        "active": True,
        "job_id": job.job_id,
        "status": job.status,
        "event_count": len(job.events),
    }


@app.get("/api/conversations/{conversation_id}/job/stream")
async def reconnect_job_stream(
    conversation_id: str,
    after: int = Query(default=0, ge=0),
):
    """
    Reconnect to a job's event stream.
    Replays buffered events from `after` index, then goes live.
    Works for both active and recently-completed jobs.
    """
    # Try active job first, then fall back to any job for this conversation
    job = job_manager.get_active_job(conversation_id)
    if job is None:
        # Check if there's a completed job we can still replay
        job = job_manager.get_any_job(conversation_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No job found for this conversation")

    return StreamingResponse(
        _stream_job_events(job, start_index=after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Job-Id": job.job_id,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
