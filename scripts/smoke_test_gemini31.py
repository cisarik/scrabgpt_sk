from __future__ import annotations

from dotenv import load_dotenv
from google.genai import types

from scrabgpt.ai.vertex_genai_client import build_client, vertex_error_hint


def main() -> None:
    load_dotenv(override=False)

    model_id = "gemini-3.1-pro-preview"
    client, config = build_client(model=model_id, verbose=True)

    print(
        f"Smoke test: model={model_id} project={config.project_id} "
        f"location={config.location}"
    )

    try:
        response = client.models.generate_content(
            model=model_id,
            contents="Ahoj, odpíš jednou vetou po slovensky.",
            config=types.GenerateContentConfig(
                max_output_tokens=256,
                thinking_config=types.ThinkingConfig(include_thoughts=True),
            ),
        )
    except Exception as exc:  # noqa: BLE001
        hint = vertex_error_hint(str(exc), model_id=model_id, location=config.location)
        print(f"FAILED: {exc}")
        if hint:
            print(f"Hint: {hint}")
        raise

    text = (response.text or "").strip()
    print("Response text:")
    print(text if text else "<empty>")

    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        total_tokens = getattr(usage, "total_token_count", None)
        print(
            "Usage metadata: "
            f"prompt={prompt_tokens} output={output_tokens} total={total_tokens}"
        )


if __name__ == "__main__":
    main()
