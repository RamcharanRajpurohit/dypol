"""Data shapes for the hybrid RAG layer.

Plain ``@dataclass`` (not pydantic) on purpose: these are internal,
hot-path value objects passed between the chunker, embedder, store, and
retriever — no validation/serialization overhead needed. The public tool
output (``semantic_search``) is shaped to a plain dict in ``retriever.py``,
so nothing here crosses the API boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Kind = Literal["code", "prose"]


@dataclass(slots=True)
class Chunk:
    """One indexable unit — a code symbol/window or a prose card."""

    text: str
    kind: str  # "code" | "prose"
    repo: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    lang: str | None = None
    sha: str | None = None
    # For prose cards (PRs/issues/commits): the PR/issue number or short sha.
    ref_number: int | None = None
    url: str | None = None

    def metadata(self) -> dict[str, object]:
        """Flat, scalar-only metadata for the vector store (Chroma rejects
        ``None`` and nested values, so we coerce/drop them)."""
        md: dict[str, object] = {"kind": self.kind, "repo": self.repo}
        for key in (
            "path",
            "start_line",
            "end_line",
            "symbol",
            "lang",
            "sha",
            "ref_number",
            "url",
        ):
            val = getattr(self, key)
            if val is not None:
                md[key] = val
        return md


@dataclass(slots=True)
class RetrievedChunk:
    """A ``Chunk`` plus its fused retrieval score and resolved source URL."""

    text: str
    kind: str
    repo: str
    score: float
    source_url: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    lang: str | None = None
    sha: str | None = None
    ref_number: int | None = None
    url: str | None = None

    @classmethod
    def from_chunk(cls, chunk: Chunk, score: float, source_url: str) -> RetrievedChunk:
        return cls(
            text=chunk.text,
            kind=chunk.kind,
            repo=chunk.repo,
            score=score,
            source_url=source_url,
            path=chunk.path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol=chunk.symbol,
            lang=chunk.lang,
            sha=chunk.sha,
            ref_number=chunk.ref_number,
            url=chunk.url,
        )


@dataclass(slots=True)
class IndexCursor:
    """Resumable per-(install, repo) bookkeeping, persisted in Mongo."""

    install_id: int
    repo: str
    last_sha: str | None = None
    last_indexed_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    chunk_count: int = 0
    embedder_model: str = ""
    dim: int = 0

    def to_doc(self) -> dict[str, object]:
        return {
            "install_id": self.install_id,
            "repo": self.repo,
            "last_sha": self.last_sha,
            "last_indexed_at": self.last_indexed_at,
            "chunk_count": self.chunk_count,
            "embedder_model": self.embedder_model,
            "dim": self.dim,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, object]) -> IndexCursor:
        return cls(
            install_id=int(doc["install_id"]),  # type: ignore[arg-type]
            repo=str(doc["repo"]),
            last_sha=doc.get("last_sha"),  # type: ignore[arg-type]
            last_indexed_at=doc.get("last_indexed_at")  # type: ignore[arg-type]
            or datetime.now(UTC),
            chunk_count=int(doc.get("chunk_count", 0) or 0),  # type: ignore[arg-type]
            embedder_model=str(doc.get("embedder_model", "") or ""),
            dim=int(doc.get("dim", 0) or 0),  # type: ignore[arg-type]
        )
