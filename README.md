# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT 5.2, Google Gemini 3.1 Pro, Anthropic Claude Opus 4.6, etc.), you can group them into your "LLM Council". This repo is a local web app that essentially looks like ChatGPT except it uses OpenRouter to send your query to multiple LLMs, it then asks them to review and rank each other's work, and finally a Chairman LLM produces the final response. Responses are streamed in real-time via SSE, and models can use web search tools during Stage 1.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected with real-time streaming. Models can optionally use web search and URL fetching tools to gather current information. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight. A leaderboard shows the consensus ranking.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user.

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Keys

Create a `.env` file in the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
BRAVE_SEARCH_API_KEY=...  # Optional: enables web search tools for council models
```

Get your OpenRouter API key at [openrouter.ai](https://openrouter.ai/). Make sure to purchase the credits you need, or sign up for automatic top up.

The Brave Search API key is optional — get one at [brave.com/search/api](https://brave.com/search/api/) if you want models to be able to search the web during Stage 1.

### 3. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "moonshotai/kimi-k2.5",
    "minimax/minimax-m2.5",
    "z-ai/glm-5",
    "openai/gpt-5.2-pro",
    "openai/gpt-5.1-codex-max",
    "google/gemini-3.1-pro-preview",
]

CHAIRMAN_MODEL = "anthropic/claude-opus-4.6"
```

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API, Brave Search API
- **Frontend:** React 19 + Vite 7, Streamdown (markdown rendering), Tailwind CSS 4, Three.js (visual effects)
- **Streaming:** Server-Sent Events (SSE) with durable job system and reconnection support
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
