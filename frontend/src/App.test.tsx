import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { API_BASE, ApiError, getHealth } from "./api/client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
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
  it("renders the shell and home page", () => {
    renderAt("/");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "SolidarityNode" })).toBeInTheDocument();
  });

  it("shows backend health on the health page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string) =>
        Promise.resolve(
          input.endsWith("/health")
            ? jsonResponse({ status: "ok" })
            : jsonResponse({
                name: "solidaritynode-backend",
                version: "0.0.1",
                core_version: "0.0.1",
              }),
        ),
      ),
    );
    renderAt("/health");
    expect(await screen.findByTestId("health-status")).toHaveTextContent("Backend status: ok");
  });

  it("shows an error when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    renderAt("/health");
    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
  });
});
