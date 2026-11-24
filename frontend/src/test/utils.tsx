import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { vi } from "vitest";

import { SessionContext, type Session } from "../app/session";
import { I18nProvider } from "../i18n/I18nProvider";

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (url: string, init: { method: string; body: string | null }) => unknown;

/** Stub `fetch` with a router of `METHOD path` handlers; unknown requests answer 404. */
export function stubApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request =
      input instanceof Request
        ? input
        : new Request(new URL(input instanceof URL ? input.href : input, "http://localhost"), init);
    const url = new URL(request.url, "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const body = request.method === "GET" ? null : await request.text();
    calls.push({ method: request.method, path, body: body ? (JSON.parse(body) as unknown) : null });
    for (const [key, handler] of Object.entries(routes)) {
      const [method, pattern] = key.split(" ");
      if (
        method === request.method &&
        pattern !== undefined &&
        new RegExp(`^${pattern}$`).test(path)
      ) {
        return jsonResponse(handler(path, { method: request.method, body }));
      }
    }
    return jsonResponse({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const SESSION: Session = {
  config: {
    deployment_mode: "municipality",
    basemap: "blank",
    app_env: "test",
    version: "0.0.1",
    git_commit: "abc",
    diagnostic_label: "Diagnostic model: not a research result",
  },
  user: { id: 1, username: "analyst", role: "analyst", active: true },
  activeDataVersion: null,
  loading: false,
  login: () => Promise.resolve(),
  logout: () => Promise.resolve(),
  refreshDataVersion: () => Promise.resolve(),
};

export function renderWithSession(
  element: ReactNode,
  {
    path = "/",
    route = "/",
    session = {},
  }: { path?: string; route?: string; session?: Partial<Session> } = {},
) {
  return render(
    <I18nProvider>
      <SessionContext.Provider value={{ ...SESSION, ...session }}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={route} element={element} />
          </Routes>
        </MemoryRouter>
      </SessionContext.Provider>
    </I18nProvider>,
  );
}
