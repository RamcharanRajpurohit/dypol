// Sentry browser init — Next.js loads this on every client page load.
// Inert without NEXT_PUBLIC_SENTRY_DSN. Session replay is sampled at 0 for
// normal sessions and 100% of sessions that hit an error, so the (student
// pack) replay quota is spent only where it helps debugging.
import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";

// PostHog product analytics — auto-captures pageviews, clicks, and web
// vitals once initialized. Inert without the token.
if (process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN) {
  posthog.init(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    // Pinned recommended-settings bundle (see PostHog SDK defaults docs).
    defaults: "2026-05-30",
  });
}

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  tracesSampleRate: 0.1,
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 1.0,
  integrations: [Sentry.replayIntegration()],
});

// Instruments client-side navigations for tracing.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
