from dataclasses import dataclass

import chromadb

from app.config import get_settings
from app.services.chunker import Chunk

COLLECTION_NAME = "document_chunks"


@dataclass
class RetrievedChunk:
    document_id: str
    filename: str
    page_number: int
    text: str
    score: float  # cosine similarity, 1.0 = identical


class VectorStore:
    """Stores chunk vectors in a persistent ChromaDB collection.

    We pass our own Gemini embeddings, so Chroma's built-in embedding
    function is disabled. The collection records which model/dimension it
    was built with, and refuses to start if the config no longer matches.
    """

    def __init__(self) -> None:
        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={
                "embedding_model": settings.embedding_model,
                "embedding_dim": settings.embedding_dim,
            },
        )

        stored = self._collection.metadata or {}
        if (stored.get("embedding_model"), stored.get("embedding_dim")) != (
            settings.embedding_model,
            settings.embedding_dim,
        ):
            raise RuntimeError(
                f"Vector store was built with {stored.get('embedding_model')} "
                f"({stored.get('embedding_dim')} dims) but config uses "
                f"{settings.embedding_model} ({settings.embedding_dim} dims). "
                f"Delete {settings.chroma_dir} and re-index your documents."
            )

    def add_chunks(
        self,
        document_id: str,
        owner_id: str,
        filename: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        self._collection.add(
            ids=[f"{document_id}:{c.chunk_index}" for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "document_id": document_id,
                    "owner_id": owner_id,
                    "filename": filename,
                    "page_number": c.page_number,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        )

    @staticmethod
    def _owner_filter(owner_id: str, document_id: str | None) -> dict:
        # Every search is restricted to the caller's own chunks.
        if document_id:
            return {"$and": [{"owner_id": owner_id}, {"document_id": document_id}]}
        return {"owner_id": owner_id}

    def search(
        self,
        query_embedding: list[float],
        top_k: int,
        owner_id: str,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]:
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=self._owner_filter(owner_id, document_id),
            include=["documents", "metadatas", "distances"],
        )
        return [
            RetrievedChunk(
                document_id=meta["document_id"],
                filename=meta["filename"],
                page_number=meta["page_number"],
                text=text,
                score=1.0 - distance,
            )
            for text, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]

    def has_documents(self, owner_id: str) -> bool:
        result = self._collection.get(where={"owner_id": owner_id}, limit=1, include=[])
        return bool(result["ids"])

    def delete_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})


vector_store = VectorStore()
