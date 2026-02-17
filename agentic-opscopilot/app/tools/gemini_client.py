from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, List

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"  # supported by Gemini API

# Free tier ~5 req/min; throttle after each call to stay under limit
_DEFAULT_THROTTLE_S = 12


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def extract_structured_json(prompt: str) -> Dict[str, Any]:
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=1024,
    )
    out = None
    text = ""

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(60)
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=config,
                )
            else:
                raise

        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        try:
            out = json.loads(text)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(f"Invalid JSON from Gemini:\n{text}")

    if out is None:
        raise RuntimeError(f"Invalid JSON from Gemini:\n{text}")

    # Throttle after each Gemini call to avoid 429 (free tier 5/min)
    throttle_s = int(os.environ.get("GEMINI_THROTTLE_S", str(_DEFAULT_THROTTLE_S)))
    if throttle_s > 0:
        time.sleep(throttle_s)

    return out


def extract_structured_json_array(prompt: str) -> List[Dict[str, Any]]:
    """
    Same as extract_structured_json but expects a JSON array. Returns list of dicts.
    Used for batch extraction (multiple emails in one call). Higher output token limit.
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=4096,
    )
    out = None
    text = ""

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(60)
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=config,
                )
            else:
                raise

        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                out = parsed
            else:
                out = [parsed] if isinstance(parsed, dict) else []
            break
        except json.JSONDecodeError:
            if attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(f"Invalid JSON from Gemini:\n{text}")

    if out is None:
        raise RuntimeError(f"Invalid JSON from Gemini:\n{text}")

    throttle_s = int(os.environ.get("GEMINI_THROTTLE_S", str(_DEFAULT_THROTTLE_S)))
    if throttle_s > 0:
        time.sleep(throttle_s)

    return out