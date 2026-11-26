/**
 * The one API client of the frontend. Types come from `schema.d.ts`, generated from the
 * backend OpenAPI schema (`make schemas`); there are no hand-written copies of backend types.
 *
 * All requests go to `API_BASE` (default `/api`), which the Vite dev server and the nginx
 * container both proxy to the backend, so the session cookie stays same-origin.
 */

import createClient from "openapi-fetch";
import type { FeatureCollection } from "geojson";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type Version = Schemas["Version"];

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

/** Git commit the frontend bundle was built from (`VITE_GIT_COMMIT`, set at image build). */
export const FRONTEND_COMMIT: string =
  (import.meta.env.VITE_GIT_COMMIT as string | undefined) ?? "unknown";

export class ApiError extends Error {
  readonly status: number;
  readonly problems: string[];

  constructor(status: number, message: string, problems: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problems = problems;
  }
}

/** Absolute form of `API_BASE` (openapi-fetch builds `Request` objects, which need one). */
export const BASE_URL = new URL(API_BASE, globalThis.location.origin).toString().replace(/\/$/, "");

export const api = createClient<paths>({
  baseUrl: BASE_URL,
  credentials: "same-origin",
  fetch: (request: Request) => globalThis.fetch(request),
});

function describe(detail: unknown, status: number): { message: string; problems: string[] } {
  if (typeof detail === "string") {
    return { message: detail, problems: [] };
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((d: { loc?: unknown[]; msg?: string }) =>
      [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
    );
    return { message: parts.join("; "), problems: [] };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; problems?: string[] };
    return { message: d.message ?? `HTTP ${String(status)}`, problems: d.problems ?? [] };
  }
  return { message: `HTTP ${String(status)}`, problems: [] };
}

/** Return `data` of an openapi-fetch result, or throw an {@link ApiError}. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || data === undefined) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    const { message, problems } = describe(detail, response.status);
    throw new ApiError(response.status, message, problems);
  }
  return data;
}

async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
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

/** A map layer of a data version as GeoJSON (EPSG:4326). */
export async function getLayer(dataVersionId: number, layer: string): Promise<FeatureCollection> {
  return (await getJson(
    `/data-versions/${String(dataVersionId)}/layers/${layer}`,
  )) as FeatureCollection;
}

/** Groups and services of a data version. */
export async function getCatalog(dataVersionId: number): Promise<Schemas["CatalogOut"]> {
  return unwrap(
    api.GET("/data-versions/{data_version_id}/catalog", {
      params: { path: { data_version_id: dataVersionId } },
    }),
  );
}

export function exportUrl(runId: string, format: "csv" | "gpkg"): string {
  return `${API_BASE}/runs/${runId}/export?format=${format}`;
}
