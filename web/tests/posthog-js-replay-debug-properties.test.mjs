import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// posthog-js 1.453.3 is the first release that stops attaching session-replay
// debug properties ($sdk_debug_replay_*, $sdk_debug_session_start, ...) to
// captured events while session replay is off (recording disabled, consent
// opted out, or remote config says replay is not enabled). Older releases sent
// those properties on every event even when nothing was being recorded.
const MIN_FIXED_VERSION = [1, 453, 3];

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

test("posthog-js dependency range omits replay debug properties when replay is off", () => {
  const manifest = readJson("../package.json");
  const range = manifest.dependencies["posthog-js"];

  assert.ok(range, "posthog-js must remain a runtime dependency");
  assert.ok(
    atLeast(parseVersion(range), MIN_FIXED_VERSION),
    `posthog-js ${range} predates 1.453.3, which stops sending session ` +
      `replay debug properties on events captured while replay is off`,
  );
});

test("locked posthog-js version omits replay debug properties when replay is off", () => {
  const lockfile = readJson("../package-lock.json");
  const locked = lockfile.packages["node_modules/posthog-js"];

  assert.ok(locked, "package-lock.json must lock posthog-js");
  assert.ok(
    atLeast(parseVersion(locked.version), MIN_FIXED_VERSION),
    `locked posthog-js ${locked.version} predates 1.453.3, which stops ` +
      `sending session replay debug properties on events captured while ` +
      `replay is off`,
  );
});
