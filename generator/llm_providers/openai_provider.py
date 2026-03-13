"""
OpenAI (GPT) LLM Provider — uses function calling for structured output.
"""
import json
import logging
import os

from generator.llm_providers.base import LLMProvider
from generator.llm_providers.registry import register


@register
class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider using function calling for structured output."""

    PROVIDER_ID = "openai"
    DISPLAY_NAME = "GPT (OpenAI)"

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key)
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

        # Convert Anthropic-style tool schema to OpenAI function calling format
        openai_tool = {
            "type": "function",
            "function": {
                "name": output_schema["name"],
                "description": output_schema.get("description", ""),
                "parameters": output_schema["input_schema"],
            },
        }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[openai_tool],
                tool_choice={
                    "type": "function",
                    "function": {"name": output_schema["name"]},
                },
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                args = msg.tool_calls[0].function.arguments
                parsed = json.loads(args)
                return parsed.get("tests", [])

            logging.warning("[OpenAI] No tool_calls in response")
            return []

        except Exception as e:
            logging.error(f"[OpenAI] API call failed: {e}")
            return []
