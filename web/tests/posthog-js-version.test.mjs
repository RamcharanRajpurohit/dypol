import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// posthog-js 1.453.2 is the first release whose survey submit button takes
// its accessible name from the visible/configured text instead of the
// hard-coded English label "Submit survey".
const MIN_FIXED_VERSION = [1, 453, 2];

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

test("posthog-js dependency range includes the survey accessible-name fix", () => {
  const manifest = readJson("../package.json");
  const range = manifest.dependencies["posthog-js"];

  assert.ok(range, "posthog-js must remain a runtime dependency");
  assert.ok(
    atLeast(parseVersion(range), MIN_FIXED_VERSION),
    `posthog-js ${range} predates 1.453.2, which names survey submit buttons ` +
      `by their visible text instead of "Submit survey"`,
  );
});

test("locked posthog-js version includes the survey accessible-name fix", () => {
  const lockfile = readJson("../package-lock.json");
  const locked = lockfile.packages["node_modules/posthog-js"];

  assert.ok(locked, "package-lock.json must lock posthog-js");
  assert.ok(
    atLeast(parseVersion(locked.version), MIN_FIXED_VERSION),
    `locked posthog-js ${locked.version} predates 1.453.2, which names ` +
      `survey submit buttons by their visible text instead of "Submit survey"`,
  );
});
