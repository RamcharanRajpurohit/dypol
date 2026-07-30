import type { Repo } from "@/lib/api";

/**
 * Render a repo's open-PR count.
 *
 * List views count open PRs with a single capped org-wide search sweep rather
 * than one request per repo. On very busy accounts that sweep doesn't reach
 * every PR, and the backend flags those counts as lower bounds — shown as
 * "78+" so the number is never presented as exact when it isn't. The repo
 * detail view queries a single repo and is always exact.
 */
export function formatPrCount(repo: Pick<Repo, "open_prs" | "open_prs_approx">): string {
  return repo.open_prs_approx ? `${repo.open_prs}+` : String(repo.open_prs);
}
