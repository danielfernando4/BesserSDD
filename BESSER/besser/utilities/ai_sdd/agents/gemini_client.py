"""
Gemini API Client with automatic model fallback.

Tries each model in order until one succeeds, handling 404/429/503 errors
by moving to the next available model. Each model has separate daily quotas
on the free tier.
"""

import logging
import json
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Models ordered by reliability / free-tier availability
# Each model has SEPARATE daily quotas on the free tier
MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
]

# Retry-able HTTP status codes
_RETRYABLE_CODES = {429, 500, 503}


class GeminiClient:
    """Gemini API client with automatic model fallback and retry logic."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._exhausted_models: set[str] = set()
        self._last_successful_model: Optional[str] = None

    def _get_model_order(self) -> list[str]:
        """Return models in priority order, putting last successful first."""
        models = [m for m in MODELS if m not in self._exhausted_models]
        if self._last_successful_model and self._last_successful_model in models:
            models.remove(self._last_successful_model)
            models.insert(0, self._last_successful_model)
        return models

    def generate(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.7,
        max_retries: int = 2,
        response_json: bool = False,
    ) -> str:
        """Generate text using the Gemini API with automatic fallback.

        Args:
            prompt: The user prompt to send.
            system_instruction: Optional system instruction.
            temperature: Sampling temperature (0.0 - 1.0).
            max_retries: Max retries per model before moving to next.
            response_json: If True, request JSON output.

        Returns:
            The generated text response.

        Raises:
            RuntimeError: If all models are exhausted.
        """
        import urllib.request
        import urllib.error

        models = self._get_model_order()
        if not models:
            self._exhausted_models.clear()
            models = self._get_model_order()

        last_error = None

        for model_name in models:
            for attempt in range(max_retries + 1):
                try:
                    result = self._call_api(
                        model_name=model_name,
                        prompt=prompt,
                        system_instruction=system_instruction,
                        temperature=temperature,
                        response_json=response_json,
                    )
                    self._last_successful_model = model_name
                    return result

                except urllib.error.HTTPError as e:
                    status = e.code
                    last_error = e

                    if status == 404:
                        logger.warning(f"[Gemini] Model '{model_name}' not found (404). Skipping.")
                        self._exhausted_models.add(model_name)
                        break  # Skip to next model

                    if status in _RETRYABLE_CODES:
                        wait = min(2 ** attempt, 8)
                        logger.warning(
                            f"[Gemini] Model '{model_name}' returned {status}. "
                            f"Retry {attempt + 1}/{max_retries} in {wait}s."
                        )
                        if attempt < max_retries:
                            time.sleep(wait)
                        else:
                            logger.warning(f"[Gemini] Exhausted retries for '{model_name}'. Moving on.")
                            self._exhausted_models.add(model_name)
                            break
                    else:
                        logger.error(f"[Gemini] Model '{model_name}' returned non-retryable {status}.")
                        self._exhausted_models.add(model_name)
                        break

                except Exception as e:
                    last_error = e
                    logger.error(f"[Gemini] Unexpected error with '{model_name}': {e}")
                    if attempt >= max_retries:
                        self._exhausted_models.add(model_name)
                        break
                    time.sleep(1)

        error_msg = f"All Gemini models exhausted. Last error: {last_error}"
        logger.error(f"[Gemini] {error_msg}")
        raise RuntimeError(error_msg)

    def _call_api(
        self,
        model_name: str,
        prompt: str,
        system_instruction: str,
        temperature: float,
        response_json: bool,
    ) -> str:
        """Make a single API call to a specific Gemini model."""
        import urllib.request
        import urllib.error

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={self.api_key}"
        )

        body: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 16384,
            },
        }

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        if response_json:
            body["generationConfig"]["responseMimeType"] = "application/json"

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Extract text from the response
        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in Gemini response")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("No parts in Gemini response candidate")

        text = parts[0].get("text", "")
        if not text:
            raise ValueError("Empty text in Gemini response")

        logger.info(f"[Gemini] Success with model '{model_name}' ({len(text)} chars)")
        return text

    def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.3,
    ) -> dict:
        """Generate a JSON response, parsing it from the model output.

        Tries JSON mode first, falls back to extracting JSON from text.
        """
        try:
            raw = self.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                response_json=True,
            )
            return json.loads(raw)
        except (json.JSONDecodeError, RuntimeError):
            pass

        # Fallback: request text and extract JSON block
        raw = self.generate(
            prompt=prompt + "\n\nRespond ONLY with valid JSON, no markdown fences.",
            system_instruction=system_instruction,
            temperature=temperature,
            response_json=False,
        )
        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from text that may contain markdown fences."""
        cleaned = text.strip()

        # Try direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Remove markdown fences
        if "```json" in cleaned:
            start = cleaned.index("```json") + 7
            end = cleaned.index("```", start)
            cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.index("```") + 3
            end = cleaned.index("```", start)
            cleaned = cleaned[start:end].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Last resort: find first { and last }
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            try:
                return json.loads(cleaned[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract JSON from response: {text[:200]}...")
