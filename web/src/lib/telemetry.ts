"use client";

import posthog from "posthog-js";
import * as Sentry from "@sentry/nextjs";

/**
 * Unified client telemetry identity + product events.
 *
 * - `identify` ties Sentry and PostHog to the signed-in GitHub user, so
 *   issues carry `user.email`/`user.username` and PostHog funnels can track
 *   real users instead of anonymous `distinct_id`s.
 * - `trackOnboarding` emits the explicit funnel events for the sign-in →
 *   connected-workspace flow, which autocapture can't reliably reconstruct
 *   (custom UI, redirects, rate-limit retries).
 *
 * Everything is fire-and-forget and no-ops when the SDKs are unconfigured
 * (no DSN / token) — telemetry must never break onboarding.
 */

export interface TelemetryUser {
  login: string;
  email: string | null;
  name: string | null;
  avatar_url: string | null;
}

let identified = false;

export function identifyUser(user: TelemetryUser): void {
  if (identified) return;
  identified = true;
  try {
    // PostHog: sets distinct_id + person properties.
    posthog.identify(user.login, {
      email: user.email ?? undefined,
      name: user.name ?? user.login,
      avatar_url: user.avatar_url ?? undefined,
      github_login: user.login,
    });
  } catch {
    // posthog not initialized (no token) — ignore.
  }
  try {
    // Sentry: attaches user context to every future event/error.
    Sentry.setUser({
      username: user.login,
      email: user.email ?? undefined,
      name: user.name ?? undefined,
      // avatar not supported by Sentry's user shape; skip.
    });
  } catch {
    // Sentry not initialized (no DSN) — ignore.
  }
}

/** Clear identity on sign-out so the next user isn't attributed to the last. */
export function resetTelemetryUser(): void {
  identified = false;
  try {
    posthog.reset();
  } catch {
    // ignore
  }
  try {
    Sentry.setUser(null);
  } catch {
    // ignore
  }
}

/** Explicit onboarding funnel events — the steps autocapture can't see. */
export type OnboardingStep =
  | "signin_clicked"
  | "oauth_redirecting"
  | "signed_in"
  | "default_workspace_added"
  | "default_workspace_failed"
  | "install_returned"
  | "workspace_connected";

export function trackOnboarding(step: OnboardingStep, extra?: Record<string, unknown>): void {
  try {
    posthog.capture("onboarding_" + step, extra);
  } catch {
    // ignore — telemetry never blocks the app
  }
}
