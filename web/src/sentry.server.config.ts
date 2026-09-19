// Sentry server-side init (Node runtime). Loaded via src/instrumentation.ts.
// No NEXT_PUBLIC_SENTRY_DSN ⇒ the SDK stays disabled — zero overhead.
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  tracesSampleRate: 0.1,
});
