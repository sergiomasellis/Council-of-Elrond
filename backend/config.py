"""Configuration for the LLM Council."""

import os
import json
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Brave Search API key
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")

# Default council members - list of OpenRouter model identifiers
DEFAULT_COUNCIL_MODELS = [
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "moonshotai/kimi-k2.5",
    "minimax/minimax-m2.5",
    "z-ai/glm-5",
    "openai/gpt-5.2-pro",
    "openai/gpt-5.1-codex-max",
    "google/gemini-3.1-pro-preview"
]

# Default chairman model - synthesizes final response
DEFAULT_CHAIRMAN_MODEL = "anthropic/claude-opus-4.6"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# Config file for persistent settings
CONFIG_FILE = "data/config.json"

# --- Dynamic config ---

_active_config = {
    "council_models": list(DEFAULT_COUNCIL_MODELS),
    "chairman_model": DEFAULT_CHAIRMAN_MODEL,
}


def load_config():
    """Load config from disk, or write defaults if not found."""
    global _active_config
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            _active_config["council_models"] = data.get("council_models", list(DEFAULT_COUNCIL_MODELS))
            _active_config["chairman_model"] = data.get("chairman_model", DEFAULT_CHAIRMAN_MODEL)
    except (FileNotFoundError, json.JSONDecodeError):
        # Write defaults to disk
        save_config()


def save_config():
    """Persist current config to disk."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(_active_config, f, indent=2)


def get_council_models():
    """Return the current list of council models."""
    return list(_active_config["council_models"])


def get_chairman_model():
    """Return the current chairman model."""
    return _active_config["chairman_model"]


def update_config(council_models, chairman_model):
    """Update and persist the config."""
    _active_config["council_models"] = list(council_models)
    _active_config["chairman_model"] = chairman_model
    save_config()
