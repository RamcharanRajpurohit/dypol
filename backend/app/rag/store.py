"""Vector store abstraction — tenant-scoped, backend-pluggable.

Chroma (embedded, default) needs no server and ships as a hard dep, so RAG
works locally with zero infra. Postgres/pgvector and Qdrant are real
implementations that activate only when their optional dep is installed,
else their constructor raises a clear "install the extra" error.

Every backend is tenant-scoped: Chroma by per-tenant collection name,
pgvector/Qdrant by an ``install_id`` filter that ``query`` ALWAYS injects.
All heavy clients are imported lazily inside ``__init__``.

The tenant id is an install id for App workspaces and a NEGATIVE account id
for public ones (see ``app/rag/tenant.py``). The stored field keeps its
``install_id`` name so existing indexes stay readable; read it as "tenant".
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from app.core.config import get_settings
from app.rag.models import Chunk

log = logging.getLogger("dypol.rag.store")


@runtime_checkable
class VectorStore(Protocol):
    def upsert(
        self, chunks: list[Chunk], vectors: list[list[float]], ids: list[str]
    ) -> None: ...

    def query(
        self, vector: list[float], k: int, where: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]: ...

    def delete_by_repo(self, repo: str) -> None: ...

    def count(self) -> int: ...


# ──────────────────────────────────────────────────────────────────────
# Chroma (default)
# ──────────────────────────────────────────────────────────────────────
class ChromaVectorStore:
    """Embedded Chroma — one collection per tenant (``tenant_{id}``)."""

    def __init__(self, tenant_id: int) -> None:
        import chromadb

        self.install_id = tenant_id  # tenant namespace; see app/rag/tenant.py
        s = get_settings()
        self._client = chromadb.PersistentClient(path=s.chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=f"tenant_{tenant_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self, chunks: list[Chunk], vectors: list[list[float]], ids: list[str]
    ) -> None:
        if not chunks:
            return
        documents = [c.text for c in chunks]
        metadatas: list[dict[str, Any]] = []
        for c in chunks:
            md = c.metadata()
            md["install_id"] = self.install_id  # always carry tenant id
            metadatas.append(md)
        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self, vector: list[float], k: int, where: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]:
        flt: dict[str, Any] = {"install_id": self.install_id}
        if where:
            for key, val in where.items():
                if key != "install_id":
                    flt[key] = val
        # Chroma wants {"$and":[...]} when more than one predicate is present.
        if len(flt) > 1:
            chroma_where: dict[str, Any] = {
                "$and": [{k: v} for k, v in flt.items()]
            }
        else:
            chroma_where = flt
        res = self._collection.query(
            query_embeddings=[vector],
            n_results=max(1, k),
            where=chroma_where,
            include=["metadatas", "documents", "distances"],
        )
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        out: list[tuple[str, float, dict[str, Any]]] = []
        for i, _id in enumerate(ids):
            dist = dists[i] if i < len(dists) else 1.0
            score = 1.0 - float(dist)  # cosine distance → similarity
            md = dict(metas[i]) if i < len(metas) and metas[i] else {}
            if i < len(docs) and docs[i] is not None:
                md.setdefault("text", docs[i])
            out.append((_id, score, md))
        return out

    def delete_by_repo(self, repo: str) -> None:
        try:
            self._collection.delete(
                where={"$and": [{"install_id": self.install_id}, {"repo": repo}]}
            )
        except Exception as exc:
            log.warning("chroma delete_by_repo(%s) failed: %s", repo, exc)

    def count(self) -> int:
        try:
            return int(self._collection.count())
        except Exception:
            return 0

    def all_docs(
        self, where: dict[str, Any] | None = None, limit: int | None = None
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Pull (id, document, metadata) for a tenant — used to build the BM25
        candidate pool. Not part of the Protocol; Chroma-specific helper."""
        flt: dict[str, Any] = {"install_id": self.install_id}
        if where:
            for key, val in where.items():
                if key != "install_id":
                    flt[key] = val
        chroma_where = (
            {"$and": [{k: v} for k, v in flt.items()]} if len(flt) > 1 else flt
        )
        try:
            res = self._collection.get(
                where=chroma_where,
                include=["documents", "metadatas"],
                limit=limit,
            )
        except Exception as exc:
            log.warning("chroma all_docs failed: %s", exc)
            return []
        ids = res.get("ids") or []
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        out: list[tuple[str, str, dict[str, Any]]] = []
        for i, _id in enumerate(ids):
            doc = docs[i] if i < len(docs) else ""
            md = dict(metas[i]) if i < len(metas) and metas[i] else {}
            out.append((_id, doc or "", md))
        return out


# ──────────────────────────────────────────────────────────────────────
# pgvector (Postgres) — real impl, activates with the optional dep
# ──────────────────────────────────────────────────────────────────────
class PgVectorStore:
    """Postgres + pgvector. One table, ``install_id``-filtered."""

    def __init__(self, tenant_id: int) -> None:
        import importlib.util

        if importlib.util.find_spec("psycopg") is None:
            raise RuntimeError(
                "pgvector backend needs psycopg — `pip install psycopg[binary] pgvector`"
            )
        s = get_settings()
        if not s.pgvector_dsn:
            raise RuntimeError("VECTOR_BACKEND=pgvector requires PGVECTOR_DSN")

        import psycopg

        self.install_id = tenant_id  # tenant namespace; see app/rag/tenant.py
        self._dsn = s.pgvector_dsn
        self._conn = psycopg.connect(self._dsn, autocommit=True)
        self._table = "rag_chunks"
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id TEXT PRIMARY KEY,
                    install_id BIGINT NOT NULL,
                    repo TEXT,
                    kind TEXT,
                    document TEXT,
                    metadata JSONB,
                    embedding vector
                );
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {self._table}_inst_idx "
                f"ON {self._table} (install_id);"
            )

    def upsert(
        self, chunks: list[Chunk], vectors: list[list[float]], ids: list[str]
    ) -> None:
        if not chunks:
            return
        import json as _json

        with self._conn.cursor() as cur:
            for chunk, vec, _id in zip(chunks, vectors, ids, strict=True):
                md = chunk.metadata()
                md["install_id"] = self.install_id
                cur.execute(
                    f"""
                    INSERT INTO {self._table}
                        (id, install_id, repo, kind, document, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding;
                    """,
                    (
                        _id,
                        self.install_id,
                        chunk.repo,
                        chunk.kind,
                        chunk.text,
                        _json.dumps(md),
                        str(vec),
                    ),
                )

    def query(
        self, vector: list[float], k: int, where: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]:
        clauses = ["install_id = %s"]
        where_params: list[Any] = [self.install_id]
        if where:
            if where.get("repo"):
                clauses.append("repo = %s")
                where_params.append(where["repo"])
            if where.get("kind"):
                clauses.append("kind = %s")
                where_params.append(where["kind"])
        where_sql = " AND ".join(clauses)
        vec_str = str(vector)
        # Param order follows %s appearance: SELECT score-vector, WHERE
        # predicates, ORDER-BY vector, LIMIT.
        params: list[Any] = [vec_str, *where_params, vec_str, max(1, k)]
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, document, metadata,
                       1 - (embedding <=> %s::vector) AS score
                FROM {self._table}
                WHERE {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                params,
            )
            rows = cur.fetchall()
        out: list[tuple[str, float, dict[str, Any]]] = []
        for row in rows:
            _id, doc, md, score = row
            md = dict(md or {})
            md.setdefault("text", doc)
            out.append((_id, float(score), md))
        return out

    def delete_by_repo(self, repo: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE install_id = %s AND repo = %s;",
                (self.install_id, repo),
            )

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM {self._table} WHERE install_id = %s;",
                (self.install_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0


# ──────────────────────────────────────────────────────────────────────
# Qdrant — real impl, activates with the optional dep
# ──────────────────────────────────────────────────────────────────────
class QdrantVectorStore:
    """Qdrant. Single collection, ``install_id`` payload filter."""

    def __init__(self, tenant_id: int) -> None:
        import importlib.util

        if importlib.util.find_spec("qdrant_client") is None:
            raise RuntimeError(
                "qdrant backend needs qdrant-client — `pip install qdrant-client`"
            )
        s = get_settings()
        if not s.qdrant_url:
            raise RuntimeError("VECTOR_BACKEND=qdrant requires QDRANT_URL")

        from qdrant_client import QdrantClient

        self.install_id = tenant_id  # tenant namespace; see app/rag/tenant.py
        self._collection = "rag_chunks"
        self._client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key)

    def _ensure_collection(self, dim: int) -> None:
        from qdrant_client import models as qmodels

        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qmodels.VectorParams(
                    size=dim, distance=qmodels.Distance.COSINE
                ),
            )

    def upsert(
        self, chunks: list[Chunk], vectors: list[list[float]], ids: list[str]
    ) -> None:
        if not chunks:
            return
        from qdrant_client import models as qmodels

        self._ensure_collection(len(vectors[0]))
        points = []
        for chunk, vec, _id in zip(chunks, vectors, ids, strict=True):
            md = chunk.metadata()
            md["install_id"] = self.install_id
            md["text"] = chunk.text
            points.append(
                qmodels.PointStruct(id=_id, vector=vec, payload=md)
            )
        self._client.upsert(collection_name=self._collection, points=points)

    def query(
        self, vector: list[float], k: int, where: dict[str, Any] | None = None
    ) -> list[tuple[str, float, dict[str, Any]]]:
        from qdrant_client import models as qmodels

        must = [
            qmodels.FieldCondition(
                key="install_id",
                match=qmodels.MatchValue(value=self.install_id),
            )
        ]
        if where:
            for key in ("repo", "kind"):
                if where.get(key):
                    must.append(
                        qmodels.FieldCondition(
                            key=key, match=qmodels.MatchValue(value=where[key])
                        )
                    )
        try:
            hits = self._client.search(
                collection_name=self._collection,
                query_vector=vector,
                query_filter=qmodels.Filter(must=must),
                limit=max(1, k),
                with_payload=True,
            )
        except Exception as exc:
            log.warning("qdrant query failed: %s", exc)
            return []
        out: list[tuple[str, float, dict[str, Any]]] = []
        for h in hits:
            md = dict(h.payload or {})
            out.append((str(h.id), float(h.score), md))
        return out

    def delete_by_repo(self, repo: str) -> None:
        from qdrant_client import models as qmodels

        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="install_id",
                                match=qmodels.MatchValue(value=self.install_id),
                            ),
                            qmodels.FieldCondition(
                                key="repo", match=qmodels.MatchValue(value=repo)
                            ),
                        ]
                    )
                ),
            )
        except Exception as exc:
            log.warning("qdrant delete_by_repo(%s) failed: %s", repo, exc)

    def count(self) -> int:
        from qdrant_client import models as qmodels

        try:
            res = self._client.count(
                collection_name=self._collection,
                count_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="install_id",
                            match=qmodels.MatchValue(value=self.install_id),
                        )
                    ]
                ),
            )
            return int(res.count)
        except Exception:
            return 0


# ──────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────
def get_vector_store(tenant_id: int) -> VectorStore:
    """Build the configured backend bound to one tenant."""
    backend = get_settings().vector_backend.strip().lower()
    if backend == "chroma":
        return ChromaVectorStore(tenant_id)
    if backend == "pgvector":
        return PgVectorStore(tenant_id)
    if backend == "qdrant":
        return QdrantVectorStore(tenant_id)
    raise RuntimeError(f"unknown VECTOR_BACKEND {backend!r}")
