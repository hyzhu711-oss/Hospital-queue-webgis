"""Load only model settings from an ignored local file, without logging values."""
import os
from pathlib import Path
from dotenv import dotenv_values

KEYS = ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY', 'LLM_EXTRA_BODY')


def load_model_env(path=None):
    source = Path(path) if path else Path(__file__).resolve().parents[1] / '.env'
    if source.is_file():
        for key, value in dotenv_values(source, interpolate=False).items():
            if key in KEYS and value and key not in os.environ:
                os.environ[key] = value.strip()
    return {key: bool(os.getenv(key, '').strip()) for key in KEYS[:3]}
