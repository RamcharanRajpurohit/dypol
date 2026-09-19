"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

let activeQueryClient: QueryClient | null = null;

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        gcTime: 30 * 60_000,
        refetchOnMount: false,
        refetchOnReconnect: false,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}

export function ApiQueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(createQueryClient);
  activeQueryClient = client;

  return (
    <QueryClientProvider client={client}>
      {children}
    </QueryClientProvider>
  );
}

export function getApiQueryClient(): QueryClient | null {
  return activeQueryClient;
}
