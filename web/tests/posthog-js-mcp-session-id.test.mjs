import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// PostHog publishes posthog-js and @posthog/mcp in the same release train.
// The train that carries @posthog/mcp 1.8.1 (an undelivered conversation
// handle no longer sets $session_id) publishes posthog-js 1.455.2. Keep the
// browser SDK on that train so the vendored PostHog packages stay aligned.
const MIN_FIXED_VERSION = [1, 455, 2];

function parseVersion(value) {
  const match = /(\d+)\.(\d+)\.(\d+)/.exec(value);
  assert.ok(match, `unreadable semver version: ${value}`);
  return match.slice(1, 4).map(Number);
}

function atLeast(version, minimum) {
  for (let i = 0; i < minimum.length; i++) {
    if (version[i] !== minimum[i]) return version[i] > minimum[i];
  }
  return true;
}

function readJson(relativePath) {
  return JSON.parse(
    readFileSync(new URL(relativePath, import.meta.url), "utf8"),
  );
}

test("posthog-js dependency range includes the MCP 1.8.1 release train", () => {
  const manifest = readJson("../package.json");
  const range = manifest.dependencies["posthog-js"];

  assert.ok(range, "posthog-js must remain a runtime dependency");
  assert.ok(
    atLeast(parseVersion(range), MIN_FIXED_VERSION),
    `posthog-js ${range} predates the 1.455.2 release train, which ships ` +
      `with @posthog/mcp 1.8.1 and its undelivered-handle $session_id fix`,
  );
});

test("locked posthog-js version includes the MCP 1.8.1 release train", () => {
  const lockfile = readJson("../package-lock.json");
  const locked = lockfile.packages["node_modules/posthog-js"];

  assert.ok(locked, "package-lock.json must lock posthog-js");
  assert.ok(
    atLeast(parseVersion(locked.version), MIN_FIXED_VERSION),
    `locked posthog-js ${locked.version} predates the 1.455.2 release train, ` +
      `which ships with @posthog/mcp 1.8.1 and its undelivered-handle ` +
      `$session_id fix`,
  );
});
