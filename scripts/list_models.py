from __future__ import annotations

import os

from dotenv import load_dotenv

from scrabgpt.ai.vertex_genai_client import build_client

_KNOWN_GEMINI_MODELS = (
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
)


def _collect_models(client: object) -> list[object]:
    try:
        return list(client.models.list())  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        print(f"models.list() failed: {exc}")
        print("Falling back to models.get() probing for known Gemini model IDs...")

    discovered: list[object] = []
    for model_id in _KNOWN_GEMINI_MODELS:
        try:
            info = client.models.get(model=model_id)  # type: ignore[attr-defined]
        except Exception:
            continue
        discovered.append(info)
    return discovered


def main() -> None:
    load_dotenv(override=False)

    requested_model = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
    client, config = build_client(model=requested_model, verbose=True)

    print(
        f"Listing models for project={config.project_id} "
        f"location={config.location} model={config.model}"
    )
    print("Available Gemini models (filtered):")

    found_any = False
    found_gemini31 = False

    for model_info in _collect_models(client):
        name = str(getattr(model_info, "name", "") or "")
        display_name = str(getattr(model_info, "display_name", "") or "-")
        haystack = f"{name} {display_name}".lower()
        if "gemini" not in haystack:
            continue

        print(f"- name={name} | display_name={display_name}")
        found_any = True

        if "gemini-3.1-pro-preview" in haystack:
            found_gemini31 = True

    if not found_any:
        print("No Gemini models were returned by Vertex for this account/location.")
    elif found_gemini31:
        print("Detected gemini-3.1-pro-preview in model list.")
    else:
        print("gemini-3.1-pro-preview not found in filtered output.")


if __name__ == "__main__":
    main()
