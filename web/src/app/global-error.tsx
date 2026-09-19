"use client";

// App Router's last-resort error boundary — replaces the root layout when a
// render error escapes everything else, so it must render its own <html>.
// Also forwards the error to Sentry (no-op when Sentry is disabled).
import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

// global-error replaces the root layout, so the stylesheet imported there is
// not in the tree — import it here or the classes below render unstyled.
import "./globals.css";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4">
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <button
          className="rounded border px-4 py-2 text-sm"
          onClick={() => reset()}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
