# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites. The system supports real-time SSE streaming, multi-turn conversations, and tool-augmented responses (web search, URL fetching).

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of OpenRouter model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- Uses environment variables from `.env`:
  - `OPENROUTER_API_KEY` (required)
  - `BRAVE_SEARCH_API_KEY` (optional, enables web search tools)
- Backend runs on **port 8001** (NOT 8000)

**`openrouter.py`**
- `query_model()`: Single async model query (non-streaming)
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- `query_model_stream()`: Streaming single model query with full tool-calling loop
  - Supports OpenAI-compatible tool definitions
  - Manages tool execution budget (max 5 rounds per query)
  - After budget exhausted, forces final answer without tools
  - Executes tools in parallel within each round
- `query_models_stream()`: Parallel streaming queries via asyncio queues
- `query_models_stream_per_model()`: Parallel streaming where each model gets its own message history
- `_estimate_tokens()` / `_msgs_tokens()`: Token estimation helpers
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`council.py`** - The Core Logic
- `build_stage1_history()`: Builds per-model chat histories from conversation history for multi-turn context
- `build_stage3_history()`: Builds chairman chat history from prior conversation turns
- `stage1_collect_responses()`: Parallel queries to all council models (non-streaming)
- `stage1_collect_responses_stream()`: Async generator streaming variant with tool support (web search, URL fetch)
- `stage2_collect_rankings()`: Anonymized peer ranking (non-streaming)
  - Anonymizes responses as "Response A, B, C, etc."
  - Creates `label_to_model` mapping for de-anonymization
  - Returns tuple: (rankings_list, label_to_model_dict)
  - Each ranking includes raw text and `parsed_ranking` list
- `stage2_collect_rankings_stream()`: Async generator streaming variant yielding (model, chunk, label_to_model) tuples
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings (non-streaming)
- `stage3_synthesize_final_stream()`: Async generator emitting event dicts with types: model_info, content_chunk, complete
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section, handles both numbered lists and plain format
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations
- `generate_conversation_title()`: Uses `google/gemini-2.5-flash` to generate short conversation titles
- `run_full_council()`: Top-level orchestrator that runs all 3 stages and returns (stage1, stage2, stage3, metadata)

**`jobs.py`** - Durable Streaming Job System
- `Job` dataclass: Tracks in-flight council pipeline state
  - Fields: job_id, conversation_id, query, status, events list, stage results, metadata
  - Status progression: pending -> stage1 -> stage2 -> stage3 -> complete | error
  - Uses `asyncio.Event` for coordination with SSE listeners
- `JobManager` class: In-memory job registry (singleton `job_manager`)
  - Maps both job_id -> Job and conversation_id -> job_id
  - Methods: `create_job()`, `get_job()`, `get_active_job()`, `get_any_job()`, `append_event()`, `cleanup_old_jobs()`
- `run_council_pipeline()`: Streaming pipeline orchestrator
  - Calls streaming variants of all 3 stages
  - Emits typed SSE events: stage1_start/init/chunk/complete, stage2_start/map/init/chunk/complete, stage3_start/init/chunk/complete, title_complete, complete, error
  - Progressive storage saves after each stage via `upsert_assistant_message()`
  - Handles multi-turn conversation history
  - Auto-generates title on first message (best-effort)
- `_save_partial_assistant()`: Helper for progressive saves

**`search.py`** - Web Search and URL Fetching Tools
- `SEARCH_TOOLS`: OpenAI-compatible tool definitions for `web_search` and `fetch_url`
- `brave_search()`: Queries Brave's LLM Context API (`/res/v1/llm/context`)
  - Requires `BRAVE_SEARCH_API_KEY`
  - Returns formatted summary + top 5 web results
- `fetch_url()`: Fetches URL content with HTML stripping
  - Truncates to 20,000 chars (`FETCH_MAX_CHARS`)
  - Lightweight HTML -> plain text via `_strip_html()`
- `execute_search_tool()`: Dispatcher that routes tool calls by name

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, title, messages[]}`
- `add_assistant_message()`: Appends a new assistant message with stage1/stage2/stage3
- `upsert_assistant_message()`: Progressive updates identified by `job_id`
  - Supports partial updates (stages can be None)
  - Includes `status` field tracking pipeline progress
  - Includes `metadata` field (label_to_model, aggregate_rankings)
  - Metadata IS persisted to storage via this method
- `update_conversation_title()`: Sets the conversation title
- `save_conversation()`: Writes full conversation to disk (used by orphan recovery)

**`main.py`**
- FastAPI app with CORS enabled for localhost:5173 and localhost:3000
- Lifecycle management:
  - On startup: marks orphaned in-progress messages as "error"
  - Background task: cleans up completed jobs older than 1 hour, every 5 minutes
- REST endpoints:
  - `GET /` - Health check
  - `GET /api/conversations` - List conversations (metadata: id, created_at, title, message_count)
  - `POST /api/conversations` - Create a new conversation
  - `GET /api/conversations/{id}` - Get full conversation with messages
  - `DELETE /api/conversations/{id}` - Delete a conversation
  - `POST /api/conversations/{id}/message` - Non-streaming council process (returns complete response)
- Streaming endpoints (SSE):
  - `POST /api/conversations/{id}/message/stream` - Start streaming council pipeline; spawns background task; returns 409 if job already running
  - `GET /api/conversations/{id}/job/status` - Check if an active job exists
  - `GET /api/conversations/{id}/job/stream?after=N` - Reconnect to job stream; replays buffered events from index N; works for active and recently-completed jobs

### Frontend Structure (`frontend/src/`)

**Tech stack:** React 19, Vite 7, Tailwind CSS 4, Streamdown (markdown), Three.js (visual effects)

**`App.jsx`**
- Main orchestration: manages conversations, theme, and streaming state
- Dark/light theme support with localStorage persistence and system preference detection
- SSE streaming with event-driven state updates via `updateLastAssistant` callback
- Job reconnection: detects incomplete assistant messages on load and reconnects to active jobs
- Handles 409 conflict when a job is already running

**`api.js`**
- API client with base URL `http://localhost:8001`
- CRUD methods for conversations
- `sendMessageStream()`: Initiates SSE stream, returns EventSource-like interface with `onEvent` callback
- `getJobStatus()`: Checks for active job on a conversation
- `reconnectJobStream()`: Reconnects to existing job stream with `after` index for replay
- `_readSSEStream()`: Internal helper that reads SSE stream and dispatches parsed events

**`components/Sidebar.jsx`**
- Navigation sidebar with conversation history list
- Shows conversation titles, message counts, delete buttons
- Theme toggle (dark/light)
- Mobile responsive drawer with toggle button

**`components/ChatInterface.jsx`**
- Main chat area layout with message list and input
- Empty state with PixelBlast visual effect
- Loading indicators per stage with status messages
- Mobile menu button for sidebar toggle

**`components/ChatInput.jsx`**
- Textarea with auto-height resizing
- Web Speech API integration for voice input with mic button
- Character counter with 3,000 character limit
- Enter to send, Shift+Enter for new line
- Loading state disables input during processing

**`components/MessageBubble.jsx`**
- Renders user and assistant messages
- Status-aware: shows stage-specific loading messages ("Council members are thinking...", "Peer review in progress...", "Chairman is synthesizing...")
- Handles interrupted/error states with notice UI for partial results

**`components/Markdown.jsx`**
- Uses **Streamdown** library (NOT ReactMarkdown) with plugins:
  - `@streamdown/code`: Syntax highlighting via Shiki (themes: github-light, github-dark-default)
  - `@streamdown/mermaid`: Diagram rendering
- Supports streaming animation via `isAnimating` prop
- Wrapped in `markdown-content` div for styling

**`components/Stage1.jsx`**
- Agent selector (chip/tab view) for individual model responses
- Streamdown rendering with streaming animation support

**`components/Stage2.jsx`**
- Tab view showing raw evaluation text from each model
- Client-side de-anonymization of model names for display
- "Extracted Ranking" shown below each evaluation for validation
- Leaderboard/Consensus Ranking section with visual bars, average position, vote count, and "Winner" badge

**`components/Stage3.jsx`**
- Final synthesized answer from chairman
- Chairman badge showing "Synthesized by {modelName}"
- Styled with teal accent border (not green background)

**`components/PixelBlast.tsx`**
- Three.js + WebGL visual effect component using postprocessing library
- Configurable: pixel size, shape variants, pattern density, ripple effects, liquid distortion, edge fade
- Interactive pointer events for ripple generation
- ResizeObserver for responsive rendering

**`components/Icons.jsx`**
- Collection of custom SVG icon components used throughout the UI

**Styling**
- Dual theme system (dark and light) via CSS custom properties in `index.css`
- Dark theme is the default
- Tailwind CSS 4 via `@tailwindcss/vite` plugin
- Streamdown-specific overrides in `index.css` using `:where()` selectors for specificity management
- Global `.markdown-content` class for markdown spacing

## Key Design Decisions

### Streaming Architecture
The system uses Server-Sent Events (SSE) for real-time streaming:
- Backend spawns a background `asyncio.Task` so the pipeline survives client disconnects
- Events are buffered in the `Job` object, enabling reconnection from any point
- Frontend can reconnect to an in-progress job via `GET .../job/stream?after=N`
- Keepalive comments sent every 30 seconds to prevent connection timeouts
- Progressive saves: assistant messages are persisted after each stage completes

### Tool-Augmented Responses
Stage 1 models can use web search and URL fetching tools:
- Tools are provided as OpenAI-compatible function definitions
- Tool-calling loop runs up to 5 rounds per model query
- After budget exhaustion, the model is forced to produce a final answer
- Brave Search API provides web search; direct HTTP fetch provides URL content

### Stage 2 Prompt Format
The Stage 2 prompt is very specific to ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "anthropic/claude-opus-4.6", ...}`
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- On startup, orphaned in-progress messages are marked as "error"
- Job failures emit error events and persist error status to storage

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`). Run as `python -m backend.main` from project root.

### Port Configuration
- Backend: 8001
- Frontend: 5173 (Vite default)
- Update both `backend/main.py` and `frontend/src/api.js` if changing

### Markdown Rendering
Uses Streamdown library with `@streamdown/code` and `@streamdown/mermaid` plugins. All Streamdown components are wrapped in `<div className="markdown-content">`. The `isAnimating` prop enables token-by-token streaming animation.

### Model Configuration
Models are hardcoded in `backend/config.py`. Chairman can be same or different from council members. Title generation uses hardcoded `google/gemini-2.5-flash`.

### Message Schema
Assistant messages in storage can have two shapes:
- **Legacy** (non-streaming): `{role, stage1, stage2, stage3}`
- **Streaming** (via upsert): `{role, job_id, status, stage1, stage2, stage3, metadata}`

Status values: pending, stage1, stage2, stage3, complete, error

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
4. **Job Conflicts**: Only one streaming job per conversation at a time (409 on duplicate)
5. **Orphaned Jobs**: If the server crashes mid-pipeline, orphaned messages are marked as "error" on next startup
6. **Search Tools**: Web search requires `BRAVE_SEARCH_API_KEY` in `.env`; without it, models won't have search capability
7. **Root main.py**: The root `main.py` is a scratch/test script for zeranker (unrelated to the council app) — do not confuse with `backend/main.py`

## Testing Notes

Use `test_openrouter.py` to verify API connectivity and test different model identifiers before adding to council.

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel streaming queries (with optional tool calls) → [individual responses]
    ↓ (progressive save)
Stage 2: Anonymize → Parallel streaming ranking queries → [evaluations + parsed rankings]
    ↓ (progressive save + aggregate rankings)
Stage 3: Chairman streaming synthesis with full context
    ↓ (progressive save)
Title generation (first message only, best-effort)
    ↓
Complete: final save with status=complete
    ↓
Frontend: SSE event stream → progressive UI updates with streaming animation
```

The entire flow is async/parallel where possible. SSE events are buffered for reconnection.
