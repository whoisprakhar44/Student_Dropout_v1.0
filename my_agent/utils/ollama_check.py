"""Ollama connectivity and model availability checks."""

from __future__ import annotations

import os

import requests


def chat_model_name() -> str:
    return os.getenv("OLLAMA_CHAT_MODEL", "qwen3.5:9b")


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def list_ollama_models() -> list[str]:
    response = requests.get(f"{ollama_base_url()}/api/tags", timeout=10)
    response.raise_for_status()
    return [m.get("name", "") for m in response.json().get("models", [])]


def model_is_available(model: str | None = None) -> bool:
    target = model or chat_model_name()
    available = list_ollama_models()
    return any(
        name == target
        or name.startswith(f"{target}:")
        or target in name
        for name in available
    )


def check_ollama() -> dict:
    model = chat_model_name()
    try:
        available = list_ollama_models()
        ok = model_is_available(model)
        return {
            "ollama": "ok",
            "model": model,
            "model_available": ok,
            "available_models": available,
        }
    except Exception as exc:
        return {
            "ollama": "error",
            "model": model,
            "model_available": False,
            "error": str(exc),
        }
