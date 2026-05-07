import { type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";

/** Build a fresh provider stack — fresh QueryClient per test isolates caches. */
export function makeWrapper({ initialPath = "/" }: { initialPath?: string } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactNode,
  options: { initialPath?: string } & Omit<RenderOptions, "wrapper"> = {},
) {
  const { initialPath, ...rest } = options;
  return render(ui, { wrapper: makeWrapper({ initialPath }), ...rest });
}
