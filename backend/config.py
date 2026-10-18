"""Single source of truth for Pitchroom's environment configuration.

The public app uses one repository-root `.env` file. Provider code can still
read environment variables dynamically (which keeps tests and local overrides
predictable), but names and defaults live here instead of being duplicated in
multiple modules.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

# Keep this map intentionally boring and explicit. It documents the supported
# configuration surface and makes a missing variable safe for the no-key demo.
DEFAULTS: dict[str, str] = {
    "PITCH_DOCUMENT_PATH": "./data/pitch.txt",
    "MAX_DOCUMENT_CHARS": "50000",
    "MAX_DOCUMENT_BYTES": str(25 * 1024 * 1024),
    "MAX_AUDIO_BYTES": str(10 * 1024 * 1024),
    "PITCHROOM_ACCESS_TOKEN": "",
    "PITCHROOM_DATABASE_PATH": "backend/data/pitchroom.sqlite3",
    "FRONTEND_ORIGINS": (
        "http://127.0.0.1:8501,http://localhost:8501,"
        "http://localhost:3000,http://localhost:5173"
    ),
    "ANSWER_GENERATION_PROVIDER": "extractive",
    "RETRIEVAL_PROVIDER": "lexical",
    "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
    "OPENAI_EMBEDDING_USD_PER_MILLION_TOKENS": "0.02",
    "ASR_PROVIDER": "huggingface",
    "WHISPER_MODEL": "base.en",
    "HUGGINGFACE_API_TOKEN": "",
    "HUGGINGFACE_BASE_URL": "https://router.huggingface.co/hf-inference",
    "HUGGINGFACE_ASR_MODEL": "openai/whisper-large-v3-turbo",
    "HUGGINGFACE_TEXT_MODEL": "Qwen/Qwen2.5-7B-Instruct",
    "TTS_PROVIDER": "browser",
    "KOKORO_LANG_CODE": "a",
    "KOKORO_VOICE": "af_heart",
    "KOKORO_SPEED": "0.98",
    "KOKORO_DEVICE": "auto",
    "PIPER_TTS_URL": "",
    "PIPER_TTS_VOICE": "",
    "SARVAM_API_KEY": "",
    "SARVAM_LANGUAGE_CODE": "en-IN",
    "SARVAM_SPEAKER": "shubh",
    "SARVAM_TTS_MODEL": "bulbul:v3",
    "OPENAI_API_KEY": "",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_TTS_MODEL": "gpt-4o-mini-tts",
    "OPENAI_TTS_VOICE": "alloy",
    "HUGGINGFACE_TTS_MODE": "off",
    "HUGGINGFACE_TTS_MODEL": "suno/bark-small",
    "HUGGINGFACE_TTS_VOICE": "v2/en_speaker_6",
    "HUGGINGFACE_TTS_MEDIA_TYPE": "audio/wav",
}


def load_environment() -> None:
    """Load the one root env file without overriding shell/deployment values."""

    load_dotenv(ENV_FILE, override=False)


def setting(name: str, fallback: str | None = None) -> str:
    """Return a trimmed setting using the central default catalog."""

    default = DEFAULTS.get(name, "" if fallback is None else fallback)
    return os.getenv(name, default).strip()
