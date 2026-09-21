import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

log = logging.getLogger("dypol.db")

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongo_uri, tz_aware=True)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongo_db]


async def _reconcile_installations_indexes(db: AsyncIOMotorDatabase) -> None:
    """Index shape for the ``installations`` collection, which holds BOTH
    App-install workspaces and public (open-source) workspaces.

    Public docs carry no ``install_id`` and are per-user (``owner_user_id``),
    so the original plain-unique indexes were wrong for them:

      * ``install_id`` unique — a missing field indexes as ``null``, and a
        unique index allows exactly ONE null. The second public workspace
        ever added anywhere raised DuplicateKeyError. Fixed by making the
        index PARTIAL so it only covers docs that actually have the field.
      * ``account_login`` unique — forbade two users tracking the same public
        org (which ``auth/deps.py`` explicitly supports) and forbade a public
        workspace for an org that also has an install. Replaced by a compound
        unique on (account_login, mode, owner_user_id): install docs have no
        ``mode``/``owner_user_id`` so they still collapse to one-per-login,
        while public docs stay unique per (login, owner).

    Both legacy indexes exist on deployed clusters, and Mongo rejects
    re-creating an index whose options changed, so drop-then-create.
    """
    coll = db["installations"]
    existing = {idx["name"]: idx async for idx in coll.list_indexes()}

    legacy_install = existing.get("install_id_1")
    if legacy_install is not None and "partialFilterExpression" not in legacy_install:
        await coll.drop_index("install_id_1")
    # Unique per install, but only among docs that HAVE an install_id.
    await coll.create_index(
        "install_id",
        unique=True,
        partialFilterExpression={"install_id": {"$exists": True}},
        name="install_id_1",
    )

    if "account_login_1" in existing:
        await coll.drop_index("account_login_1")
    await coll.create_index(
        [("account_login", 1), ("mode", 1), ("owner_user_id", 1)],
        unique=True,
        name="account_login_mode_owner_1",
    )
    # Plain lookup index — every workspace resolution filters on this.
    await coll.create_index("account_login", name="account_login_lookup_1")


async def init_indexes() -> None:
    db = get_db()

    # Auth & tenancy
    await db["users"].create_index("github_id", unique=True)
    await db["users"].create_index("login", unique=True)
    try:
        await _reconcile_installations_indexes(db)
    except Exception as exc:
        # A drop/create race between replicas must not abort the rest of the
        # index setup — the next boot reconciles.
        log.warning("installations index reconcile skipped: %s", exc)
    # TTL index — Mongo auto-purges expired install tokens
    await db["install_tokens"].create_index("install_id", unique=True)
    await db["install_tokens"].create_index("expires_at", expireAfterSeconds=0)

    # Domain caches (populated by background sync / webhooks)
    await db["repos"].create_index([("install_id", 1), ("full_name", 1)], unique=True)
    await db["prs"].create_index([("install_id", 1), ("repo", 1), ("number", 1)], unique=True)
    await db["prs"].create_index("updated_at")
    await db["commits"].create_index([("install_id", 1), ("repo", 1), ("sha", 1)], unique=True)
    await db["commits"].create_index("author_login")
    await db["events"].create_index("created_at")
    await db["events"].create_index([("install_id", 1), ("created_at", -1)])
    await db["members"].create_index([("install_id", 1), ("login", 1)], unique=True)
    await db["alerts"].create_index([("install_id", 1), ("kind", 1), ("ref", 1)], unique=True)

    # Ask Anything answer cache (TTL-purged)
    await db["ask_cache"].create_index("key", unique=True)
    await db["ask_cache"].create_index("expires_at", expireAfterSeconds=0)

    # Chat — sessions + messages
    await db["chat_sessions"].create_index([("user_id", 1), ("updated_at", -1)])
    await db["chat_sessions"].create_index([("user_id", 1), ("archived", 1)])
    await db["chat_messages"].create_index([("session_id", 1), ("created_at", 1)])

    # Cross-chat long-term memory — one doc per (user, org)
    await db["user_memory"].create_index([("user_id", 1), ("org", 1)], unique=True)

    # Governance — daily usage counters + audit log
    await db["usage_daily"].create_index(
        [("user_id", 1), ("org", 1), ("day", 1)], unique=True
    )
    # Per-user daily chat-call quota (app/services/quota.py)
    await db["usage_calls"].create_index(
        [("user_id", 1), ("day", 1)], unique=True
    )
    await db["audit_log"].create_index([("org", 1), ("timestamp", -1)])
    await db["audit_log"].create_index("timestamp")

    # Hybrid RAG bookkeeping (app/rag/state.py). Harmless when RAG is unused —
    # the collections simply stay empty. Guarded so a stray index error can't
    # block boot of the rest of the app.
    try:
        await db["rag_index_state"].create_index(
            [("install_id", 1), ("repo", 1)], unique=True
        )
        await db["rag_dirty"].create_index(
            [("install_id", 1), ("repo", 1), ("kind", 1), ("ref", 1)], unique=True
        )
        await db["rag_dirty"].create_index("queued_at")
    except Exception:
        # An index conflict (e.g. legacy shape) must not abort startup.
        pass


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
