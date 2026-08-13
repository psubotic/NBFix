import os

from .client import LLMClient

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5-coder:14b"


def default_client() -> LLMClient:
    """
    Builds an LLMClient from NBSYNTH_LLM_BASE_URL/NBSYNTH_LLM_MODEL env
    vars, defaulting to a local Ollama instance. Centralized here so the
    server extension and the CLI configure themselves identically.
    """
    return LLMClient(
        base_url=os.environ.get("NBSYNTH_LLM_BASE_URL", DEFAULT_BASE_URL),
        model=os.environ.get("NBSYNTH_LLM_MODEL", DEFAULT_MODEL),
    )
