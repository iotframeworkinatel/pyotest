"""
LLM Provider Abstraction — Strategy pattern for multi-provider support.

Defines the LLMProvider abstract base class that all provider adapters
must implement. This enables the test generator to swap between Claude,
OpenAI, and Gemini without changing the generation logic.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters."""

    PROVIDER_ID: str = "unknown"
    DISPLAY_NAME: str = "Unknown"

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this provider's API key is configured."""
        ...

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict,
        max_tokens: int = 8192,
    ) -> list[dict]:
        """Generate structured test output from the LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User-level prompt with device/test details.
            output_schema: Tool/function schema describing expected output.
                           Has keys: name, description, input_schema.
            max_tokens: Maximum tokens in the response.

        Returns:
            List of test dicts extracted from the LLM response.
            Each dict has: test_id, test_name, pytest_code,
            vulnerability_type, severity, references.
        """
        ...
