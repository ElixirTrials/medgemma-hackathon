#!/usr/bin/env python3
"""Verify Gemini API access using GOOGLE_API_KEY from .env.

Run from repo root:
  uv run python scripts/verify_gemini_access.py

Uses the same client and model as the extraction service; useful after
enabling Generative Language API and setting up a Cloud Console API key.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root so GOOGLE_API_KEY is available
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")


def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set in .env", file=sys.stderr)
        return 1

    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    try:
        from google import genai
    except ImportError:
        print("google-genai is not installed. Run: uv sync", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)
    print(f"Calling Gemini ({model_name}) with a simple prompt...")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Reply with exactly: OK",
        )
        text = (response.text or "").strip()
        if "OK" in text.upper():
            print("Success. Gemini API is reachable and returned:", text[:80])
            return 0
        print("Unexpected response:", text[:200], file=sys.stderr)
        return 0  # API worked, response format was odd
    except Exception as e:
        print(f"Gemini API error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
