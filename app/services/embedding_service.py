import math

from google import genai
from google.genai import types

from app.config import get_settings

# gemini-embedding-001 accepts at most 100 texts per request.
BATCH_SIZE = 100


class EmbeddingService:
    """Embeds document chunks and user queries with one fixed Gemini model.

    Using the same model and dimension for both sides is what makes query
    vectors comparable to document vectors.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
        )
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        response = await self._client.aio.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.dim,
            ),
        )
        vectors = [e.values for e in response.embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
        return [self._normalize(v) for v in vectors]

    def _normalize(self, vector: list[float]) -> list[float]:
        # gemini-embedding-001 only returns unit vectors at 3072 dims;
        # truncated sizes must be normalized by the caller.
        if len(vector) != self.dim:
            raise RuntimeError(f"Expected {self.dim}-dim embedding, got {len(vector)}")
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            vectors.extend(await self._embed(texts[i : i + BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


embedding_service = EmbeddingService()
