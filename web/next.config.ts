import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
};

// Sentry build-time wrapper: injects the SDK into client/server bundles and,
// when SENTRY_AUTH_TOKEN + SENTRY_ORG + SENTRY_PROJECT are set in CI, uploads
// source maps so stack traces are readable. Without those env vars it builds
// normally and skips the upload.
export default withSentryConfig(config, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  disableLogger: true,
  widenClientFileUpload: true,
});
