from collections.abc import AsyncIterator
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import get_settings
from app.schemas import ChatMessage

GENERAL_INSTRUCTION = (
    "You are a helpful assistant. Answer from your general knowledge. "
    "You do not have access to the user's uploaded documents in this mode."
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMService:
    """Thin async wrapper around the Gemini API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
        )
        self._model = settings.gemini_model

    @staticmethod
    def _contents(question: str, history: list[ChatMessage] | None) -> list[types.Content]:
        # Previous turns are sent as a real multi-turn conversation so Gemini
        # can resolve follow-ups like "what about the second one?".
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)],
            )
            for m in history or []
        ]
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=question)]))
        return contents

    @staticmethod
    def _config(system_instruction: str | None) -> types.GenerateContentConfig | None:
        if not system_instruction:
            return None
        return types.GenerateContentConfig(system_instruction=system_instruction)

    async def ask(
        self,
        question: str,
        system_instruction: str | None = None,
        history: list[ChatMessage] | None = None,
    ) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._contents(question, history),
            config=self._config(system_instruction),
        )
        return response.text or ""

    async def ask_stream(
        self,
        question: str,
        system_instruction: str | None = None,
        history: list[ChatMessage] | None = None,
    ) -> AsyncIterator[str]:
        """Yield the answer in pieces as Gemini generates it."""
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=self._contents(question, history),
            config=self._config(system_instruction),
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def ask_json(self, prompt: str, schema: type[SchemaT], model: str | None = None) -> SchemaT:
        """Ask for structured output that is parsed into the given Pydantic model."""
        response = await self._client.aio.models.generate_content(
            model=model or self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0,
            ),
        )
        if isinstance(response.parsed, schema):
            return response.parsed
        return schema.model_validate_json(response.text or "")


llm_service = LLMService()
