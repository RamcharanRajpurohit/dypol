"""cAST-style chunking — structure-aware for code, paragraph-aware for prose.

Code: parse with tree-sitter (via tree-sitter-language-pack), walk the top
level for function/class definitions, and emit one ``Chunk`` per symbol with
line ranges + the symbol name. Following the cAST recipe we (a) MERGE tiny
adjacent symbols up to a soft char budget so we don't bloat the index with
one-line stubs, and (b) SPLIT oversized symbols along line boundaries so a
giant class still fits the embedder context.

Anything that can't be parsed — unknown extension, syntax error, binary —
falls back to a sliding line window. This module NEVER raises: a bad file
just yields whatever chunks we could salvage (possibly none).
"""
from __future__ import annotations

import logging

from app.rag.models import Chunk

log = logging.getLogger("dypol.rag.chunker")

# Soft per-chunk size budget (chars). cAST merges below it, splits above it.
_MAX_CHUNK_CHARS = 1500
_LINE_WINDOW = 80  # fallback sliding-window size in lines
_PROSE_CHARS = 1000
_PROSE_OVERLAP = 150

# Extension → tree-sitter language id (as understood by tree_sitter_language_pack).
LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "c_sharp",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
}

# tree-sitter node types we treat as top-level "definition" boundaries,
# across languages. We don't enumerate per-language — any node whose type
# contains one of these substrings is a candidate boundary.
_DEF_HINTS: tuple[str, ...] = (
    "function",
    "method",
    "class",
    "struct",
    "interface",
    "impl",
    "module",
    "trait",
    "enum",
    "constructor",
)


def _ext_of(path: str) -> str:
    i = path.rfind(".")
    return path[i:].lower() if i != -1 else ""


def lang_for_path(path: str) -> str | None:
    return LANG_BY_EXT.get(_ext_of(path))


# ──────────────────────────────────────────────────────────────────────
# tree-sitter binding shims. The wheel bundled by tree-sitter-language-pack
# exposes a *method-based* node API (``node.kind()``, ``node.start_byte()``,
# ``tree.root_node()``), whereas classic py-tree-sitter uses attributes
# (``node.type``, ``node.start_byte``, ``tree.root_node``). These helpers
# accept either so the chunker works regardless of which binding is active.
# ──────────────────────────────────────────────────────────────────────
def _call_or_attr(obj, name):  # noqa: ANN001, ANN202
    val = getattr(obj, name)
    return val() if callable(val) else val


def _node_kind(node) -> str:
    try:
        return str(_call_or_attr(node, "kind"))
    except Exception:
        try:
            return str(node.type)
        except Exception:
            return ""


def _node_byte(node, which: str) -> int:
    return int(_call_or_attr(node, which))  # start_byte / end_byte


def _node_row(node, which: str) -> int:
    """0-based row of ``start_position``/``end_position`` (method binding) or
    ``start_point``/``end_point`` (attribute binding)."""
    try:
        pos = _call_or_attr(node, which.replace("point", "position"))
        return int(pos.row)
    except Exception:
        pass
    pos = _call_or_attr(node, which)  # start_point → (row, col) tuple
    return int(pos[0])


def _named_children(node) -> list:
    try:
        count = _call_or_attr(node, "named_child_count")
        return [node.named_child(i) for i in range(int(count))]
    except Exception:
        pass
    # Classic binding: a ``children`` list/property.
    try:
        return [c for c in node.children if getattr(c, "is_named", True)]
    except Exception:
        return []


def _root_node(tree):  # noqa: ANN001, ANN202
    rn = tree.root_node
    return rn() if callable(rn) else rn


def _node_name(node, source_bytes: bytes) -> str | None:
    """Best-effort symbol name: the node's ``name`` child if present."""
    try:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return source_bytes[
                _node_byte(name_node, "start_byte") : _node_byte(name_node, "end_byte")
            ].decode("utf-8", "replace")
    except Exception:
        pass
    # Fall back to scanning immediate children for an identifier-ish node.
    try:
        for child in _named_children(node):
            kind = _node_kind(child)
            if "identifier" in kind or kind == "name":
                return source_bytes[
                    _node_byte(child, "start_byte") : _node_byte(child, "end_byte")
                ].decode("utf-8", "replace")
    except Exception:
        pass
    return None


def _is_def(node) -> bool:
    t = _node_kind(node)
    return any(h in t for h in _DEF_HINTS)


def _split_oversized(
    repo: str,
    path: str,
    lang: str,
    sha: str | None,
    text: str,
    start_line: int,
    symbol: str | None,
) -> list[Chunk]:
    """Split a symbol whose text exceeds the budget along line boundaries."""
    lines = text.splitlines(keepends=True)
    out: list[Chunk] = []
    buf: list[str] = []
    buf_start = start_line
    cur_line = start_line
    for ln in lines:
        buf.append(ln)
        cur_line += 1
        if sum(len(x) for x in buf) >= _MAX_CHUNK_CHARS:
            body = "".join(buf)
            out.append(
                Chunk(
                    text=body,
                    kind="code",
                    repo=repo,
                    path=path,
                    start_line=buf_start,
                    end_line=cur_line - 1,
                    symbol=symbol,
                    lang=lang,
                    sha=sha,
                )
            )
            buf = []
            buf_start = cur_line
    if buf:
        body = "".join(buf)
        if body.strip():
            out.append(
                Chunk(
                    text=body,
                    kind="code",
                    repo=repo,
                    path=path,
                    start_line=buf_start,
                    end_line=cur_line - 1,
                    symbol=symbol,
                    lang=lang,
                    sha=sha,
                )
            )
    return out


def _chunk_lines(
    repo: str, path: str | None, text: str, sha: str | None, lang: str | None
) -> list[Chunk]:
    """Fallback: sliding line window, char-capped. Always succeeds."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    out: list[Chunk] = []
    i = 0
    n = len(lines)
    while i < n:
        window: list[str] = []
        start = i
        while i < n and len(window) < _LINE_WINDOW and (
            sum(len(x) for x in window) < _MAX_CHUNK_CHARS
        ):
            window.append(lines[i])
            i += 1
        body = "".join(window)
        if body.strip():
            out.append(
                Chunk(
                    text=body,
                    kind="code",
                    repo=repo,
                    path=path,
                    start_line=start + 1,
                    end_line=i,
                    symbol=None,
                    lang=lang,
                    sha=sha,
                )
            )
    return out


def chunk_code(
    repo: str, path: str, text: str, sha: str | None = None
) -> list[Chunk]:
    """Structure-aware code chunks. Falls back to line windows on any failure."""
    if not text or not text.strip():
        return []

    lang = lang_for_path(path)
    if lang is None:
        return _chunk_lines(repo, path, text, sha, None)

    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(lang)
        source_bytes = text.encode("utf-8", "replace")
        # The bundled binding wants ``str``; classic py-tree-sitter wants
        # ``bytes``. Try str first, fall back to bytes.
        try:
            tree = parser.parse(text)
        except TypeError:
            tree = parser.parse(source_bytes)
        root = _root_node(tree)
    except Exception as exc:  # parser missing / parse blew up
        log.debug("tree-sitter parse failed for %s (%s): %s", path, lang, exc)
        return _chunk_lines(repo, path, text, sha, lang)

    # Collect top-level definition nodes (and any direct children of the root
    # that aren't defs get folded into "gap" chunks so nothing is lost).
    top = _named_children(root)
    if not top:
        return _chunk_lines(repo, path, text, sha, lang)

    raw: list[Chunk] = []
    for node in top:
        try:
            body = source_bytes[
                _node_byte(node, "start_byte") : _node_byte(node, "end_byte")
            ].decode("utf-8", "replace")
            if not body.strip():
                continue
            start_line = _node_row(node, "start_point") + 1
            end_line = _node_row(node, "end_point") + 1
            symbol = _node_name(node, source_bytes) if _is_def(node) else None
            if len(body) > _MAX_CHUNK_CHARS and _is_def(node):
                raw.extend(
                    _split_oversized(
                        repo, path, lang, sha, body, start_line, symbol
                    )
                )
            else:
                ch = Chunk(
                    text=body,
                    kind="code",
                    repo=repo,
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    symbol=symbol,
                    lang=lang,
                    sha=sha,
                )
                # Tag whether this node is a definition so the merge step can
                # keep defs as their own chunks (granular symbol pointers).
                ch.lang = lang  # (already set; explicit for clarity)
                raw.append((ch, _is_def(node)))  # type: ignore[arg-type]
        except Exception:
            continue

    if not raw:
        return _chunk_lines(repo, path, text, sha, lang)

    return _merge_tiny(raw)  # type: ignore[arg-type]


def _merge_tiny(chunks: list[tuple[Chunk, bool]]) -> list[Chunk]:
    """cAST greedy merge: fold small *non-definition* nodes (imports, loose
    statements) into an adjacent chunk so we don't index one-line stubs, while
    keeping every function/class as its own chunk for granular symbol
    pointers. Each entry is ``(chunk, is_def)``."""
    if not chunks:
        return []
    merged: list[Chunk] = []
    pending: Chunk | None = None  # accumulated small non-def gap

    def flush() -> None:
        nonlocal pending
        if pending is not None and pending.text.strip():
            merged.append(pending)
        pending = None

    for ch, is_def in chunks:
        if is_def:
            # Attach any pending gap to the front of this definition if it fits.
            if (
                pending is not None
                and pending.path == ch.path
                and len(pending.text) + len(ch.text) <= _MAX_CHUNK_CHARS
            ):
                ch = Chunk(
                    text=pending.text + ch.text,
                    kind="code",
                    repo=ch.repo,
                    path=ch.path,
                    start_line=pending.start_line,
                    end_line=ch.end_line,
                    symbol=ch.symbol,
                    lang=ch.lang,
                    sha=ch.sha,
                )
                pending = None
            else:
                flush()
            merged.append(ch)
            continue

        # Non-def: accumulate into the pending gap.
        if pending is None:
            pending = ch
        elif (
            pending.path == ch.path
            and len(pending.text) + len(ch.text) <= _MAX_CHUNK_CHARS
        ):
            pending = Chunk(
                text=pending.text + ch.text,
                kind="code",
                repo=pending.repo,
                path=pending.path,
                start_line=pending.start_line,
                end_line=ch.end_line,
                symbol=pending.symbol or ch.symbol,
                lang=pending.lang,
                sha=pending.sha,
            )
        else:
            flush()
            pending = ch
    flush()
    return merged


def chunk_prose(text: str, **meta) -> list[Chunk]:
    """Paragraph-aware splitter with overlap, ~1000 chars/chunk.

    ``meta`` supplies the Chunk fields (repo required; path/url/ref_number/
    sha/symbol optional). Splits on blank-line paragraph boundaries first,
    then hard-wraps anything still too long.
    """
    if not text or not text.strip():
        return []

    repo = meta.get("repo", "")
    base = {
        "kind": "prose",
        "repo": repo,
        "path": meta.get("path"),
        "symbol": meta.get("symbol"),
        "lang": meta.get("lang"),
        "sha": meta.get("sha"),
        "ref_number": meta.get("ref_number"),
        "url": meta.get("url"),
    }

    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    units: list[str] = []
    for p in paras:
        if len(p) <= _PROSE_CHARS:
            units.append(p)
        else:
            # Hard-wrap an oversized paragraph by char windows with overlap.
            i = 0
            while i < len(p):
                units.append(p[i : i + _PROSE_CHARS])
                i += _PROSE_CHARS - _PROSE_OVERLAP

    # Greedily pack units up to the budget.
    out: list[Chunk] = []
    buf = ""
    for u in units:
        if buf and len(buf) + len(u) + 2 > _PROSE_CHARS:
            out.append(Chunk(text=buf, **base))
            # carry overlap from the tail of the previous buffer
            buf = buf[-_PROSE_OVERLAP:] + "\n\n" + u if _PROSE_OVERLAP else u
        else:
            buf = f"{buf}\n\n{u}" if buf else u
    if buf.strip():
        out.append(Chunk(text=buf, **base))
    return out
