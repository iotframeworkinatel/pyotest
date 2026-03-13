"""
Google Gemini LLM Provider — uses JSON mode with response_schema for structured output.
"""
import json
import logging
import os

from generator.llm_providers.base import LLMProvider
from generator.llm_providers.registry import register


def _anthropic_schema_to_gemini(input_schema: dict) -> dict:
    """Convert the Anthropic tool input_schema to a Gemini-compatible response_schema.

    Gemini's response_schema expects a top-level object; we extract the
    'tests' array definition and wrap it as the response type.
    """
    tests_schema = (
        input_schema.get("properties", {})
        .get("tests", {})
        .get("items", {})
    )
    return {
        "type": "ARRAY",
        "items": _convert_type(tests_schema),
    }


def _convert_type(schema: dict) -> dict:
    """Recursively convert JSON Schema types to Gemini Schema format."""
    t = schema.get("type", "string").upper()
    result: dict = {"type": t}

    if t == "OBJECT":
        props = {}
        for k, v in schema.get("properties", {}).items():
            props[k] = _convert_type(v)
        result["properties"] = props
        if "required" in schema:
            result["required"] = schema["required"]
    elif t == "ARRAY":
        result["items"] = _convert_type(schema.get("items", {"type": "string"}))
    elif "enum" in schema:
        result["enum"] = schema["enum"]

    return result


@register
class GeminiProvider(LLMProvider):
    """Google Gemini provider using JSON mode for structured output."""

    PROVIDER_ID = "gemini"
    DISPLAY_NAME = "Gemini (Google)"

    def __init__(self):
        self.api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict,
        max_tokens: int = 8192,
    ) -> list[dict]:
        if not self.is_available():
            return []

        try:
            from google.genai import types

            client = self._get_client()
            gemini_schema = _anthropic_schema_to_gemini(output_schema["input_schema"])

            response = client.models.generate_content(
                model=self.model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=gemini_schema,
                    max_output_tokens=max_tokens,
                ),
            )

            parsed = json.loads(response.text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return parsed.get("tests", [])
            return []

        except Exception as e:
            logging.error(f"[Gemini] API call failed: {e}")
            return []
