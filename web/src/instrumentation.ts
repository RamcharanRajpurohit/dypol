// Next.js instrumentation hook — runs once per server/edge process start.
// https://nextjs.org/docs/app/guides/instrumentation
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// Reports errors from nested React Server Components.
export const onRequestError = Sentry.captureRequestError;
