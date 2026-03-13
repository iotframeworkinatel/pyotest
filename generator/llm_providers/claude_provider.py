"""
Claude (Anthropic) LLM Provider — uses tool use for structured output.
"""
import logging
import os

from generator.llm_providers.base import LLMProvider
from generator.llm_providers.registry import register


@register
class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider using tool use for structured output."""

    PROVIDER_ID = "claude"
    DISPLAY_NAME = "Claude (Anthropic)"

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
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

        tool_name = output_schema["name"]
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=[output_schema],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user_prompt}],
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == tool_name:
                    return block.input.get("tests", [])

            logging.warning("[Claude] No tool_use block in response")
            return []

        except Exception as e:
            logging.error(f"[Claude] API call failed: {e}")
            return []
