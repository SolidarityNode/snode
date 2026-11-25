import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { API_BASE, ApiError, getHealth } from "./api/client";
import { SessionProvider } from "./app/SessionProvider";
import { I18nProvider } from "./i18n/I18nProvider";
import { jsonResponse } from "./test/utils";

function renderAt(path: string) {
  return render(
    <I18nProvider>
      <SessionProvider>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </SessionProvider>
    </I18nProvider>,
  );
}

const VERSION = {
  name: "solidaritynode-backend",
  version: "0.0.1",
  core_version: "0.0.1",
  git_commit: "0123abcd",
  app_env: "development",
};

function urlOf(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

describe("api client", () => {
  it("calls /health under the API base", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getHealth()).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/health`, expect.any(Object));
  });

  it("raises ApiError on HTTP errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({}, 503)));
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("App", () => {
  it("sends anonymous users to the login page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          urlOf(input).endsWith("/auth/me")
            ? jsonResponse({ detail: "login required" }, 401)
            : jsonResponse(VERSION),
        ),
      ),
    );
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 2, name: "Log in" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("shows backend health on the health page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          urlOf(input).endsWith("/health") ? jsonResponse({ status: "ok" }) : jsonResponse(VERSION),
        ),
      ),
    );
    renderAt("/health");
    expect(await screen.findByTestId("health-status")).toHaveTextContent("Backend status: ok");
  });

  it("shows backend version and commit in the footer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(VERSION))),
    );
    renderAt("/health");
    expect(await screen.findByTestId("build-info")).toHaveTextContent(
      "backend 0.0.1 (0123abcd, development) · frontend",
    );
  });

  it("shows an error when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    renderAt("/health");
    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
    expect(await screen.findByTestId("build-info")).toHaveTextContent("backend unavailable");
  });
});
