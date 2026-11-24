/**
 * Minimal typed client for the SolidarityNode API.
 *
 * All requests go to `API_BASE` (default `/api`), which the Vite dev server and the nginx
 * container both proxy to the backend, so the browser never needs CORS in local setups.
 */

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

export interface Health {
  status: "ok";
}

export interface Version {
  name: string;
  version: string;
  core_version: string;
  git_commit: string;
  app_env: string;
}

/** Git commit the frontend bundle was built from (`VITE_GIT_COMMIT`, set at image build). */
export const FRONTEND_COMMIT: string =
  (import.meta.env.VITE_GIT_COMMIT as string | undefined) ?? "unknown";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed with ${String(response.status)}`);
  }
  return response.json();
}

function isHealth(value: unknown): value is Health {
  return (
    typeof value === "object" && value !== null && (value as { status?: unknown }).status === "ok"
  );
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const body = await getJson("/health", signal);
  if (!isHealth(body)) {
    throw new ApiError(500, "unexpected /health response");
  }
  return body;
}

export async function getVersion(signal?: AbortSignal): Promise<Version> {
  return (await getJson("/version", signal)) as Version;
}
