"""Google Gemini API wrapper with retry logic."""

from __future__ import annotations

import json
import re
import time

from google import genai
from google.genai import types

from .config import Config


class LLMClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = genai.Client(api_key=config.api_key)
        self.model_name = config.model
        self._last_call_time: float = 0
        self._min_interval: float = 6.0  # ~10 RPM to stay safely under free tier limits

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        max_retries: int = 8,
    ) -> dict | list:
        """Send prompt to Gemini and parse JSON from response."""
        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            response_mime_type="application/json",
        )
        if system_prompt:
            config.system_instruction = system_prompt

        for attempt in range(max_retries):
            self._rate_limit()
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                text = response.text.strip()
                return json.loads(text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                text = response.text.strip()
                match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
                if match:
                    return json.loads(match.group(1).strip())
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"  JSON parse error, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "resource" in error_str or "quota" in error_str:
                    # Parse retry delay from error if available
                    import re as _re
                    delay_match = _re.search(r"retry.*?(\d+)\.", error_str) or _re.search(r"retrydelay.*?'(\d+)s'", error_str)
                    if delay_match:
                        wait = min(int(delay_match.group(1)) + 5, 120)
                    else:
                        wait = min(2 ** (attempt + 2) * 3, 120)
                    print(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"  Error: {e}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("Max retries exceeded")

    def _rate_limit(self) -> None:
        """Enforce minimum interval between API calls."""
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()
