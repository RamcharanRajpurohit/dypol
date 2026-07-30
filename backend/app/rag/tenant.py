"""Tenant identity for the RAG index.

The index was originally keyed on ``install_id``, which silently excluded
public (open-source) workspaces — they have no installation, so they got no
index and the agent was never offered ``semantic_search``. Public repo
content is perfectly indexable; only the *namespace* needed widening.

``Tenant`` separates the two things ``install_id`` used to conflate:

  * ``id``          — the storage namespace (vector collection, cursors).
  * ``install_id``  — how to AUTHENTICATE to GitHub (``None`` ⇒ public client).

Public tenants take the **negative** GitHub account id. That keeps the
namespace an ``int`` (every store backend and all Mongo bookkeeping already
type it that way, including the pgvector BIGINT column), guarantees it can
never collide with a positive install id, and leaves existing install
tenants — their ids, their chunk ids, their Chroma collections — byte-for-byte
unchanged, so nothing needs re-indexing.

Every user tracking the same public org resolves to the SAME tenant id. That
is deliberate: the content is public and identical for all of them, so they
share one index instead of paying to embed it once per user.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Tenant:
    """A workspace, resolved into "where to store" + "how to fetch"."""

    id: int
    install_id: int | None
    login: str
    account_type: str
    is_public: bool

    @property
    def is_org(self) -> bool:
        return self.account_type != "User"


def tenant_for(workspace: dict[str, Any]) -> Tenant | None:
    """Resolve a workspace doc to a ``Tenant``, or None if it can't be indexed."""
    login = (workspace.get("account_login") or "").strip()
    if not login:
        return None
    account_type = workspace.get("account_type") or "Organization"

    install_id = workspace.get("install_id")
    if install_id is not None:
        return Tenant(
            id=int(install_id),
            install_id=int(install_id),
            login=login,
            account_type=account_type,
            is_public=False,
        )

    account_id = workspace.get("account_id")
    if account_id is None:
        # A public workspace row written before account_id was recorded —
        # nothing stable to namespace on, so skip rather than risk collisions.
        return None
    return Tenant(
        id=-abs(int(account_id)),
        install_id=None,
        login=login,
        account_type=account_type,
        is_public=True,
    )


def tenant_id_for(workspace: dict[str, Any]) -> int | None:
    """Just the storage namespace — for callers that don't need the rest."""
    tenant = tenant_for(workspace)
    return tenant.id if tenant else None
