"""Centralized Google Gen AI Vertex client configuration utilities."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from google import genai
from google.genai.types import HttpOptions

log = logging.getLogger("scrabgpt.ai.vertex_genai_client")

DEFAULT_VERTEX_MODEL = "gemini-2.5-pro"
DEFAULT_VERTEX_LOCATION = "us-central1"

_GEMINI_3_PREVIEW_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-pro",
    "gemini-3-flash-preview",
    "gemini-3-pro-image-preview",
}


@dataclass(frozen=True)
class VertexGenAIConfig:
    """Resolved Vertex Gen AI connection settings."""

    project_id: str
    location: str
    model: str
    credentials_path: str | None
    auth_mode: str
    google_genai_version: str


def _detect_google_genai_version() -> str:
    try:
        return version("google-genai")
    except PackageNotFoundError:
        return "unknown"


def _canonical_model_id(model_id: str) -> str:
    cleaned = model_id.strip()
    if cleaned.startswith("google/"):
        cleaned = cleaned[len("google/") :]
    if "/" in cleaned:
        cleaned = cleaned.rsplit("/", 1)[-1]
    return cleaned.lower()


def is_gemini_3_preview_model(model_id: str) -> bool:
    """Return True if model id belongs to Gemini 3.x preview family."""
    if not model_id.strip():
        return False
    normalized = _canonical_model_id(model_id)
    return normalized.startswith("gemini-3.") or normalized in _GEMINI_3_PREVIEW_MODELS


def _resolve_credentials_path(explicit_credentials_path: str | None = None) -> str | None:
    candidate = explicit_credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if candidate:
        resolved = Path(candidate).expanduser().resolve()
        if resolved.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(resolved)
            return str(resolved)
        log.warning("GOOGLE_APPLICATION_CREDENTIALS points to missing file: %s", resolved)
        return None

    fallback = Path("vertexaccount.json").resolve()
    if fallback.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(fallback)
        return str(fallback)

    return None


def _project_id_from_service_account(credentials_path: str) -> str | None:
    try:
        with open(credentials_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:  # noqa: BLE001
        log.warning("Could not parse service account JSON at %s", credentials_path, exc_info=True)
        return None

    project_id = payload.get("project_id")
    if isinstance(project_id, str) and project_id.strip():
        return project_id.strip()
    return None


def _resolve_project_id(
    explicit_project_id: str | None,
    credentials_path: str | None,
) -> str:
    if isinstance(explicit_project_id, str) and explicit_project_id.strip():
        return explicit_project_id.strip()

    env_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if isinstance(env_project, str) and env_project.strip():
        return env_project.strip()

    if credentials_path:
        project_id = _project_id_from_service_account(credentials_path)
        if project_id:
            return project_id

    raise ValueError(
        "Unable to resolve Google Cloud project ID. Set GOOGLE_CLOUD_PROJECT "
        "or provide GOOGLE_APPLICATION_CREDENTIALS with project_id."
    )


def _resolve_model_id(explicit_model: str | None) -> str:
    candidates = (
        explicit_model,
        os.getenv("GEMINI_MODEL"),
        os.getenv("GOOGLE_GEMINI_MODEL"),
    )
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return DEFAULT_VERTEX_MODEL


def _resolve_location(explicit_location: str | None, model_id: str) -> str:
    requested = (
        explicit_location
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or os.getenv("VERTEX_LOCATION")
    )
    requested_location = requested.strip().lower() if isinstance(requested, str) else ""
    if not requested_location:
        requested_location = (
            "global" if is_gemini_3_preview_model(model_id) else DEFAULT_VERTEX_LOCATION
        )

    if is_gemini_3_preview_model(model_id) and requested_location != "global":
        log.warning(
            "Model %s requires Vertex global endpoint. Overriding location %s -> global.",
            model_id,
            requested_location,
        )
        return "global"

    return requested_location


def resolve_vertex_genai_config(
    *,
    project_id: str | None = None,
    location: str | None = None,
    model: str | None = None,
    credentials_path: str | None = None,
    verbose: bool = True,
) -> VertexGenAIConfig:
    """Resolve connection settings for Vertex via google-genai."""
    resolved_credentials = _resolve_credentials_path(credentials_path)
    resolved_model = _resolve_model_id(model)
    resolved_location = _resolve_location(location, resolved_model)
    resolved_project = _resolve_project_id(project_id, resolved_credentials)
    sdk_version = _detect_google_genai_version()
    auth_mode = (
        f"service_account_json:{resolved_credentials}" if resolved_credentials else "adc"
    )

    config = VertexGenAIConfig(
        project_id=resolved_project,
        location=resolved_location,
        model=resolved_model,
        credentials_path=resolved_credentials,
        auth_mode=auth_mode,
        google_genai_version=sdk_version,
    )

    if verbose:
        log.info(
            (
                "Vertex Gen AI config: project_id=%s location=%s model=%s auth=%s "
                "google-genai=%s"
            ),
            config.project_id,
            config.location,
            config.model,
            config.auth_mode,
            config.google_genai_version,
        )

    return config


def build_client(
    *,
    project_id: str | None = None,
    location: str | None = None,
    model: str | None = None,
    credentials_path: str | None = None,
    verbose: bool = True,
) -> tuple[genai.Client, VertexGenAIConfig]:
    """Build a configured Vertex Gen AI client and return config alongside it."""
    config = resolve_vertex_genai_config(
        project_id=project_id,
        location=location,
        model=model,
        credentials_path=credentials_path,
        verbose=verbose,
    )
    client = genai.Client(
        vertexai=True,
        project=config.project_id,
        location=config.location,
        http_options=HttpOptions(api_version="v1"),
    )
    return client, config


def get_client(
    *,
    project_id: str | None = None,
    location: str | None = None,
    model: str | None = None,
    credentials_path: str | None = None,
    verbose: bool = True,
) -> genai.Client:
    """Build a configured Vertex Gen AI client."""
    client, _ = build_client(
        project_id=project_id,
        location=location,
        model=model,
        credentials_path=credentials_path,
        verbose=verbose,
    )
    return client


def vertex_error_hint(error_text: str, *, model_id: str, location: str) -> str | None:
    """Return operator-friendly hint for common Vertex endpoint issues."""
    lowered = error_text.lower()
    mismatch_markers = (
        "not found",
        "not_found",
        "404",
        "location",
        "publisher model",
        "does not have access",
        "permission denied",
    )
    if any(marker in lowered for marker in mismatch_markers):
        if is_gemini_3_preview_model(model_id) and location != "global":
            return (
                "Gemini 3.x preview models require location=global. "
                "Set GOOGLE_CLOUD_LOCATION=global."
            )
        return (
            "Check that Vertex AI API is enabled, IAM grants Vertex AI User, "
            "and use location=global for Gemini 3.x preview models."
        )
    return None
