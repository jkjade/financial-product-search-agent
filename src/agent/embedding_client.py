from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .ncp_client import ncp_api_key_from_env, ncp_headers


@dataclass(frozen=True)
class EmbeddingSettings:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "EmbeddingSettings | None":
        api_key = ncp_api_key_from_env()
        if api_key is None:
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv(
                "HCX_EMBEDDING_BASE_URL",
                "https://clovastudio.stream.ntruss.com",
            ).rstrip("/"),
            model=os.getenv("HCX_EMBEDDING_MODEL", "bge-m3"),
            timeout_seconds=float(os.getenv("HCX_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )


class ClovaEmbeddingClient:
    """Thin wrapper around CLOVA Studio Embedding API.

    Embeddings are only used for external/unstructured evidence. Structured product
    rows continue to use PostgreSQL filters, aggregates and ranks.
    """

    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Embedding text must not be empty")
        if len(text) > 10000:
            # Embedding v2 token calculator documents a 10,000-character Korean input bound.
            text = text[:10000]
        headers = ncp_headers(self.settings.api_key)
        if self.settings.model == "bge-m3":
            url = f"{self.settings.base_url}/v1/api-tools/embedding/v2"
        else:
            url = f"{self.settings.base_url}/v1/api-tools/embedding/{self.settings.model}"
        with httpx.Client(timeout=self.settings.timeout_seconds) as client:
            response = client.post(url, headers=headers, json={"text": text})
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        embedding = ((payload.get("result") or {}).get("embedding"))
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError("CLOVA embedding response did not contain an embedding vector")
        return [float(value) for value in embedding]
