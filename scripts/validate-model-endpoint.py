"""Validate model endpoints: test Ollama, Gemini, and extraction endpoints."""

from __future__ import annotations

import os
import sys

import httpx


def check_ollama(base_url: str) -> tuple[bool, str]:
    """Check Ollama server health and available models."""
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return True, f"OK — {len(models)} models: {models}"
    except Exception as e:
        return False, f"FAIL — {e}"


def check_ollama_model(base_url: str, model: str) -> tuple[bool, str]:
    """Test a specific Ollama model with a simple prompt."""
    try:
        resp = httpx.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": "Say 'hello' and nothing else."}
                ],
                "stream": False,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return True, f"OK — response: {content[:80]}"
    except Exception as e:
        return False, f"FAIL — {e}"


def check_gemini() -> tuple[bool, str]:
    """Check Gemini API key validity."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return False, "SKIP — GOOGLE_API_KEY not set"
    try:
        resp = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=10.0,
        )
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return True, f"OK — {len(models)} models available"
        return False, f"FAIL — HTTP {resp.status_code}"
    except Exception as e:
        return False, f"FAIL — {e}"


def main() -> None:
    """Run all health checks and print status table."""
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma2:9b")
    extraction_model = os.getenv("OLLAMA_EXTRACTION_MODEL", "qwen2.5:14b")

    checks: list[tuple[str, bool, str]] = []

    print("=" * 60)
    print("GemmaCrit Model Endpoint Validation")
    print("=" * 60)
    print()

    # Ollama server
    ok, msg = check_ollama(ollama_url)
    checks.append(("Ollama Server", ok, msg))
    print(f"  {'[PASS]' if ok else '[FAIL]'} Ollama Server: {msg}")

    if ok:
        # Grounding model
        ok2, msg2 = check_ollama_model(ollama_url, ollama_model)
        checks.append((f"Grounding ({ollama_model})", ok2, msg2))
        print(f"  {'[PASS]' if ok2 else '[FAIL]'} Grounding ({ollama_model}): {msg2}")

        # Extraction model
        ok3, msg3 = check_ollama_model(ollama_url, extraction_model)
        checks.append((f"Extraction ({extraction_model})", ok3, msg3))
        print(
            f"  {'[PASS]' if ok3 else '[FAIL]'} Extraction ({extraction_model}): {msg3}"
        )

    # Gemini API
    ok4, msg4 = check_gemini()
    checks.append(("Gemini API", ok4, msg4))
    print(f"  {'[PASS]' if ok4 else '[FAIL]'} Gemini API: {msg4}")

    print()
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Results: {passed}/{total} checks passed")

    if passed < total:
        failed = [name for name, ok, _ in checks if not ok]
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("All checks passed!")


if __name__ == "__main__":
    main()
