"""Embedding providers, content-kind routed, all lazy.

Every client is imported *inside* a method so a missing optional dep
(voyageai, openai, sentence-transformers) never breaks import or boot.
``get_embedder`` resolves the configured provider (or "auto") to a cached
instance, and ``any_embedder_available()`` is the cheap, never-raising
probe the RAG gate calls — it checks key presence + importability only,
it MUST NOT hit any provider API.

The default is Gemini: its key is already present for the agent, and
``google-genai`` is a hard dep, so RAG works out of the box with no extra
setup.
"""
from __future__ import annotations

import importlib.util
import logging
from typing import Literal, Protocol, runtime_checkable

from app.core.config import get_settings

log = logging.getLogger("dypol.rag.embeddings")

EmbedKind = Literal["code", "prose"]


@runtime_checkable
class Embedder(Protocol):
    """Minimal contract. ``embed`` is sync (called in a thread by callers)."""

    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


# ──────────────────────────────────────────────────────────────────────
# Implementations
# ──────────────────────────────────────────────────────────────────────
class GeminiEmbedder:
    """Gemini ``embed_content`` (google-genai). Default provider.

    ``text-embedding-004`` returns 768-dim vectors.
    """

    def __init__(self) -> None:
        from app.core.keypool import gemini_keys

        s = get_settings()
        if not gemini_keys():
            raise RuntimeError("No Gemini key set (GEMINI_API_KEY or GEMINI_API_KEY_1..8)")
        self.model_id = s.gemini_embed_model
        self.dim = 768
        self._client = None  # built lazily on first embed

    def _get_client(self):  # noqa: ANN202
        # Take one key from the rotating pool and keep it for this embedder's
        # lifetime: an index tick issues many batches back-to-back, and a
        # long-lived client avoids re-handshaking per batch. Different ticks /
        # embedder instances land on different keys.
        if self._client is None:
            from google import genai

            from app.core.keypool import next_gemini_key

            self._client = genai.Client(api_key=next_gemini_key())
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        resp = client.models.embed_content(model=self.model_id, contents=texts)
        out = [list(e.values) for e in resp.embeddings]
        if out and self.dim != len(out[0]):
            self.dim = len(out[0])
        return out


class VoyageEmbedder:
    """Voyage AI — best-in-class code embeddings (``voyage-code-3``)."""

    def __init__(self) -> None:
        if not _has("voyageai"):
            raise RuntimeError("voyageai not installed — `pip install voyageai`")
        s = get_settings()
        if not s.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY not set")
        self.model_id = s.voyage_code_model
        self.dim = 1024
        self._client = None

    def _get_client(self):  # noqa: ANN202
        if self._client is None:
            import voyageai

            self._client = voyageai.Client(api_key=get_settings().voyage_api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = self._get_client().embed(texts, model=self.model_id)
        out = [list(v) for v in result.embeddings]
        if out and self.dim != len(out[0]):
            self.dim = len(out[0])
        return out


class OpenAIEmbedder:
    """OpenAI embeddings (``text-embedding-3-small`` ⇒ 1536-dim)."""

    def __init__(self) -> None:
        if not _has("openai"):
            raise RuntimeError("openai not installed — `pip install openai`")
        s = get_settings()
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.model_id = s.openai_embed_model
        self.dim = 1536
        self._client = None

    def _get_client(self):  # noqa: ANN202
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=get_settings().openai_api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._get_client().embeddings.create(model=self.model_id, input=texts)
        out = [list(d.embedding) for d in resp.data]
        if out and self.dim != len(out[0]):
            self.dim = len(out[0])
        return out


class LocalEmbedder:
    """sentence-transformers, fully local. Picks the code or prose model."""

    def __init__(self, kind: EmbedKind = "prose") -> None:
        if not _has("sentence_transformers"):
            raise RuntimeError(
                "sentence-transformers not installed — `pip install sentence-transformers`"
            )
        s = get_settings()
        self.model_id = s.local_code_model if kind == "code" else s.local_prose_model
        self.dim = 0  # discovered after the model loads
        self._model = None

    def _get_model(self):  # noqa: ANN202
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_id)
            try:
                self.dim = int(self._model.get_sentence_embedding_dimension())
            except Exception:
                self.dim = 0
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        vecs = model.encode(texts, normalize_embeddings=True)
        out = [list(map(float, v)) for v in vecs]
        if out and self.dim != len(out[0]):
            self.dim = len(out[0])
        return out


# ──────────────────────────────────────────────────────────────────────
# Resolution + caching
# ──────────────────────────────────────────────────────────────────────
_cache: dict[str, Embedder | None] = {}


def _provider_available(name: str) -> bool:
    """Cheap availability check — key presence + dep importability only.
    NEVER calls a provider API (the gate runs this on every boot)."""
    s = get_settings()
    if name == "gemini":
        from app.core.keypool import gemini_keys

        return bool(gemini_keys())  # google-genai is a hard dep
    if name == "voyage":
        return bool(s.voyage_api_key) and _has("voyageai")
    if name == "openai":
        return bool(s.openai_api_key) and _has("openai")
    if name == "local":
        return _has("sentence_transformers")
    return False


# Order tried when a provider is "auto".
_AUTO_ORDER: tuple[str, ...] = ("gemini", "voyage", "openai", "local")


def _build(name: str, kind: EmbedKind) -> Embedder | None:
    """Construct a named provider, or return None if it can't be built."""
    try:
        if name == "gemini":
            return GeminiEmbedder()
        if name == "voyage":
            return VoyageEmbedder()
        if name == "openai":
            return OpenAIEmbedder()
        if name == "local":
            return LocalEmbedder(kind)
    except Exception as exc:  # missing key/dep/model — degrade, don't crash
        log.info("embedder %r unavailable: %s", name, exc)
        return None
    return None


def get_embedder(kind: EmbedKind) -> Embedder | None:
    """Resolve the embedder for a content ``kind`` ("code" | "prose").

    Honors ``EMBED_CODE_PROVIDER`` / ``EMBED_PROSE_PROVIDER``:
      * "none"      → None (that kind is disabled).
      * "auto"      → first available of gemini → voyage → openai → local.
      * a provider  → that one, or None if its key/dep is missing.
    Instances are cached per (provider, kind).
    """
    s = get_settings()
    configured = (
        s.embed_code_provider if kind == "code" else s.embed_prose_provider
    ).strip().lower()

    if configured == "none":
        return None

    if configured == "auto":
        for name in _AUTO_ORDER:
            if not _provider_available(name):
                continue
            key = f"{name}:{kind}"
            if key not in _cache:
                _cache[key] = _build(name, kind)
            if _cache[key] is not None:
                return _cache[key]
        return None

    # Explicit provider name.
    if not _provider_available(configured):
        return None
    key = f"{configured}:{kind}"
    if key not in _cache:
        _cache[key] = _build(configured, kind)
    return _cache[key]


def any_embedder_available() -> bool:
    """True if at least one embedder resolves for code or prose. Never raises
    — wrapped so a broken provider can't take down the RAG gate. Does NOT
    call any provider API (key/dep presence only)."""
    try:
        return get_embedder("prose") is not None or get_embedder("code") is not None
    except Exception as exc:  # pragma: no cover — defensive
        log.info("any_embedder_available probe failed: %s", exc)
        return False


def reset_embedder_cache() -> None:
    """Test/debug helper — clear the per-provider instance cache."""
    _cache.clear()
