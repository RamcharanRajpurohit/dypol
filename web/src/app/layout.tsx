import type { Metadata, Viewport } from "next";
import { ApiQueryProvider } from "@/lib/api/QueryProvider";
import { fontVariables } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://dypol.example.com"),
  title: {
    default: "DyPol.ai — An AI engineering analyst, not another dashboard.",
    template: "%s · DyPol.ai",
  },
  description:
    "DyPol.ai is an AI analyst that reads your GitHub data and source code, then answers any question about your engineering org.",
  applicationName: "DyPol.ai",
  authors: [{ name: "DyPol.ai" }],
  openGraph: {
    title: "DyPol.ai — An AI engineering analyst, not another dashboard.",
    description:
      "DyPol.ai is an AI analyst that reads your GitHub data and source code, then answers any question about your engineering org.",
    siteName: "DyPol.ai",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "DyPol.ai",
    description:
      "An AI analyst that reads your GitHub data and source code, then answers any question about your engineering org.",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FAF7F2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fontVariables} suppressHydrationWarning>
      <body className="text-ink" suppressHydrationWarning>
        <ApiQueryProvider>{children}</ApiQueryProvider>
      </body>
    </html>
  );
}
