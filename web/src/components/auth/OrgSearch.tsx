"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { addPublicWorkspace, ApiError, searchAccounts } from "@/lib/api";
import type { AccountSearchResult } from "@/lib/api";
import { CloseIcon, SearchIcon } from "@/components/app/icons";
import { Skeleton } from "@/components/app/Skeleton";

/**
 * Type-ahead for adding a public GitHub org/user as a read-only workspace.
 *
 * Replaces the old "type an exact login and hope" form: you search, see repo
 * counts and descriptions, and add in one click.
 *
 * Three things shape the implementation:
 *
 *  1. **Search costs a shared budget.** GitHub allows 10 searches/min
 *     anonymously (30 with a PAT) across the whole deployment, so we debounce,
 *     require a minimum query length, and skip the request entirely when the
 *     trimmed query hasn't changed. The backend memoises on top of that.
 *  2. **Responses can land out of order.** Each request carries a sequence
 *     number and stale replies are dropped, so a fast "as" reply can't
 *     overwrite a slower "astral" one.
 *  3. **Cold start needs an answer.** With an empty box we show curated
 *     open-source orgs as one-click chips — no API call until one is used.
 */

const DEBOUNCE_MS = 300;
const MIN_CHARS = 2;

/** Hand-picked starting points — all verified active, multi-repo orgs. */
const SUGGESTIONS: { login: string; hint: string }[] = [
  { login: "astral-sh", hint: "ruff · uv" },
  { login: "pallets", hint: "Flask" },
  { login: "supabase", hint: "Postgres" },
  { login: "withastro", hint: "Astro" },
  { login: "excalidraw", hint: "whiteboard" },
  { login: "kubernetes", hint: "K8s" },
];

type AddState = Record<string, "adding" | "added" | undefined>;

export function OrgSearch({ onAdded }: { onAdded?: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AccountSearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [active, setActive] = useState(-1);
  const [addState, setAddState] = useState<AddState>({});

  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  // Monotonic request id — see note 2 in the component docblock.
  const seq = useRef(0);
  const lastQuery = useRef<string>("");

  const trimmed = query.trim();
  const tooShort = trimmed.length < MIN_CHARS;

  useEffect(() => {
    if (tooShort) {
      setResults(null);
      setLoading(false);
      setError(null);
      setRateLimited(false);
      setActive(-1);
      lastQuery.current = "";
      return;
    }
    if (trimmed === lastQuery.current) return;

    setLoading(true);
    const id = ++seq.current;
    const timer = setTimeout(async () => {
      try {
        const data = await searchAccounts(trimmed, 6);
        if (id !== seq.current) return; // a newer query already went out
        lastQuery.current = trimmed;
        setResults(data.results);
        setRateLimited(data.rate_limited);
        setError(null);
        setActive(data.results.length > 0 ? 0 : -1);
      } catch (err) {
        if (id !== seq.current) return;
        setResults([]);
        setError(
          err instanceof ApiError
            ? `${err.status}: ${err.message}`
            : err instanceof Error
              ? err.message
              : String(err),
        );
      } finally {
        if (id === seq.current) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [trimmed, tooShort]);

  const add = useCallback(
    async (login: string) => {
      if (addState[login]) return;
      setAddState((s) => ({ ...s, [login]: "adding" }));
      try {
        await addPublicWorkspace(login);
        setAddState((s) => ({ ...s, [login]: "added" }));
        onAdded?.();
      } catch (err) {
        setAddState((s) => ({ ...s, [login]: undefined }));
        setError(
          err instanceof ApiError
            ? err.status === 404
              ? `No GitHub account named "${login}"`
              : `Couldn't add ${login} — ${err.status}: ${err.message}`
            : err instanceof Error
              ? err.message
              : String(err),
        );
      }
    },
    [addState, onAdded],
  );

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!results || results.length === 0) {
      if (e.key === "Escape") setQuery("");
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = results[active];
      if (hit && !hit.already_added) void add(hit.login);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setQuery("");
      inputRef.current?.focus();
    }
  };

  const showSuggestions = tooShort && !loading;

  return (
    <div style={{ textAlign: "left" }}>
      {/* ── Search field ─────────────────────────────────────────── */}
      <div style={{ position: "relative" }}>
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: 12,
            top: "50%",
            transform: "translateY(-50%)",
            color: "var(--ink3)",
            display: "flex",
            pointerEvents: "none",
          }}
        >
          <SearchIcon width={15} height={15} />
        </span>
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={!!results && results.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            active >= 0 && results?.[active]
              ? `${listId}-opt-${results[active].login}`
              : undefined
          }
          aria-label="Search GitHub organizations and users"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setError(null);
          }}
          onKeyDown={onKeyDown}
          placeholder="Search GitHub orgs — try “astral”, “kubernetes”, “flask”"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          className="bg-bg hairline focus:border-accent w-full rounded-[6px] border py-2.5 text-[13.5px] transition-colors focus:outline-none"
          style={{ paddingLeft: 34, paddingRight: 36 }}
        />
        <span
          style={{
            position: "absolute",
            right: 10,
            top: "50%",
            transform: "translateY(-50%)",
            display: "flex",
            alignItems: "center",
          }}
        >
          {loading ? (
            <Spinner />
          ) : query ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              style={{
                display: "flex",
                color: "var(--ink3)",
                background: "none",
                border: 0,
                cursor: "pointer",
                padding: 2,
              }}
            >
              <CloseIcon width={13} height={13} />
            </button>
          ) : null}
        </span>
      </div>

      {/* ── Cold start: curated orgs ──────────────────────────────── */}
      {showSuggestions && (
        <div style={{ marginTop: 14 }}>
          <div className="label-tight" style={{ marginBottom: 8 }}>
            Popular open-source orgs
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s.login}
                type="button"
                className="chip"
                onClick={() => {
                  setQuery(s.login);
                  inputRef.current?.focus();
                }}
              >
                {s.login}
                <span style={{ color: "var(--ink3)", marginLeft: 6 }}>
                  {s.hint}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-[12px]" style={{ color: "var(--ink3)" }}>
            Read-only access to public repos, commits, PRs, and issues. No
            GitHub App install required.
          </p>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────── */}
      {!tooShort && (
        <div style={{ marginTop: 12 }}>
          {loading && !results && (
            <div className="card" style={{ overflow: "hidden" }}>
              {[0, 1, 2].map((i) => (
                <ResultSkeleton key={i} />
              ))}
            </div>
          )}

          {rateLimited && (
            <Notice tone="hot">
              GitHub&rsquo;s search limit is spent for the moment (10 searches
              per minute without a token). Wait a few seconds, or set{" "}
              <code className="mono">GITHUB_PAT</code> to raise it to 30/min.
              {looksLikeLogin(trimmed) && (
                <DirectAdd
                  login={trimmed}
                  state={addState[trimmed]}
                  onAdd={() => add(trimmed)}
                />
              )}
            </Notice>
          )}

          {error && !rateLimited && <Notice tone="stuck">{error}</Notice>}

          {results && results.length === 0 && !loading && !rateLimited && !error && (
            <Notice tone="muted">
              No GitHub account matches &ldquo;{trimmed}&rdquo;.
              {looksLikeLogin(trimmed) && (
                <DirectAdd
                  login={trimmed}
                  state={addState[trimmed]}
                  onAdd={() => add(trimmed)}
                />
              )}
            </Notice>
          )}

          {results && results.length > 0 && (
            <ul
              id={listId}
              role="listbox"
              aria-label="Search results"
              className="card"
              style={{ overflow: "hidden", listStyle: "none", margin: 0, padding: 0 }}
            >
              {results.map((r, i) => (
                <ResultRow
                  key={r.login}
                  id={`${listId}-opt-${r.login}`}
                  result={r}
                  query={trimmed}
                  active={i === active}
                  state={addState[r.login]}
                  onHover={() => setActive(i)}
                  onAdd={() => add(r.login)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Pieces
// ──────────────────────────────────────────────────────────────────
function ResultRow({
  id,
  result,
  query,
  active,
  state,
  onHover,
  onAdd,
}: {
  id: string;
  result: AccountSearchResult;
  query: string;
  active: boolean;
  state: "adding" | "added" | undefined;
  onHover: () => void;
  onAdd: () => void;
}) {
  const added = state === "added" || result.already_added;
  const isOrg = result.type === "Organization";
  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      onMouseEnter={onHover}
      className="row"
      style={{
        gridTemplateColumns: "34px 1fr auto",
        gap: 12,
        padding: "12px 16px",
        background: active ? "var(--warm-tint)" : undefined,
      }}
    >
      {result.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={result.avatar_url}
          alt=""
          width={30}
          height={30}
          style={{ borderRadius: isOrg ? 6 : "50%" }}
        />
      ) : (
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: isOrg ? 6 : "50%",
            background: "var(--hairline)",
          }}
        />
      )}

      <div style={{ minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 7,
            flexWrap: "wrap",
          }}
        >
          <span className="text-[13.5px]" style={{ color: "var(--ink)" }}>
            <Highlight text={result.login} query={query} />
          </span>
          <span
            className="mono"
            style={{
              fontSize: 10,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: isOrg ? "var(--accent)" : "var(--ink3)",
              border: `1px solid ${isOrg ? "var(--accent)" : "var(--hairline2)"}`,
              borderRadius: 3,
              padding: "0 4px",
            }}
          >
            {isOrg ? "org" : "user"}
          </span>
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--ink3)",
            marginTop: 3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          <span className="mono">{result.public_repos} repos</span>
          {result.description ? ` · ${result.description}` : ""}
        </div>
      </div>

      {added ? (
        <span
          className="status-line"
          style={{ color: "var(--ok)", fontSize: 12, whiteSpace: "nowrap" }}
        >
          <span className="dot ok" />
          Added
        </span>
      ) : (
        <button
          type="button"
          className="btn-primary-sm"
          onClick={onAdd}
          disabled={state === "adding"}
          aria-label={`Add ${result.login} as a public workspace`}
        >
          {state === "adding" ? "Adding…" : "Add"}
        </button>
      )}
    </li>
  );
}

/** GitHub logins: alphanumerics and hyphens (underscores on legacy accounts). */
function looksLikeLogin(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$/.test(value);
}

/**
 * Escape hatch when search returns nothing usable. Adding by exact login hits
 * ``/users/{login}`` — the REST budget, NOT the search budget — so it still
 * works when search is rate-limited, and it covers accounts GitHub's search
 * ranks poorly.
 */
function DirectAdd({
  login,
  state,
  onAdd,
}: {
  login: string;
  state: "adding" | "added" | undefined;
  onAdd: () => void;
}) {
  if (state === "added") {
    return (
      <div style={{ marginTop: 10 }}>
        <span className="status-line" style={{ color: "var(--ok)", fontSize: 12 }}>
          <span className="dot ok" />
          Added {login}
        </span>
      </div>
    );
  }
  return (
    <div
      style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}
    >
      <button
        type="button"
        className="btn-primary-sm"
        onClick={onAdd}
        disabled={state === "adding"}
      >
        {state === "adding" ? "Adding…" : `Add “${login}” directly`}
      </button>
      <span style={{ fontSize: 11.5, color: "var(--ink3)" }}>
        if that&rsquo;s the exact login
      </span>
    </div>
  );
}

/** Bold the matched substring so scanning a result list is instant. */
function Highlight({ text, query }: { text: string; query: string }) {
  const at = text.toLowerCase().indexOf(query.toLowerCase());
  if (at < 0 || !query) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark
        style={{
          background: "transparent",
          color: "var(--ink)",
          fontWeight: 600,
        }}
      >
        {text.slice(at, at + query.length)}
      </mark>
      {text.slice(at + query.length)}
    </>
  );
}

function ResultSkeleton() {
  return (
    <div
      className="row"
      style={{ gridTemplateColumns: "34px 1fr auto", gap: 12, padding: "12px 16px" }}
    >
      <Skeleton width={30} height={30} rounded={6} />
      <div>
        <Skeleton width="45%" height={12} />
        <div style={{ marginTop: 6 }}>
          <Skeleton width="70%" height={10} />
        </div>
      </div>
      <Skeleton width={44} height={24} rounded={5} />
    </div>
  );
}

function Notice({
  tone,
  children,
}: {
  tone: "hot" | "stuck" | "muted";
  children: React.ReactNode;
}) {
  const color =
    tone === "hot" ? "var(--hot)" : tone === "stuck" ? "var(--stuck)" : "var(--ink2)";
  return (
    <div
      className="card"
      style={{ padding: "12px 14px", fontSize: 12.5, color, lineHeight: 1.5 }}
    >
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      style={{
        width: 13,
        height: 13,
        border: "1.5px solid var(--hairline2)",
        borderTopColor: "var(--accent)",
        borderRadius: "50%",
        display: "inline-block",
        animation: "dypol-spin 0.6s linear infinite",
      }}
    />
  );
}
