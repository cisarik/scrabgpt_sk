from __future__ import annotations

import os

from dotenv import load_dotenv
from google.genai import types

from scrabgpt.ai.vertex_genai_client import build_client, vertex_error_hint


def main() -> None:
    load_dotenv(override=False)

    model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip() or "gemini-2.5-pro"
    client, config = build_client(model=model_id, verbose=True)

    print(f"Testing generate_content for model={model_id} location={config.location}")

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=[
                types.Content(role="user", parts=[types.Part(text="Hello from Vertex test script.")])
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=100,
                temperature=0.7,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        hint = vertex_error_hint(str(exc), model_id=model_id, location=config.location)
        print(f"FAILED: {exc}")
        if hint:
            print(f"Hint: {hint}")
        raise

    print("SUCCESS")
    print(f"Response: {response.text}")


if __name__ == "__main__":
    main()
