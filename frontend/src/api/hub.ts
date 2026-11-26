/**
 * Client of the hub API (`/hub/*`, mounted only when `DEPLOYMENT_MODE=hub`). Types come from
 * `hub-schema.d.ts`, generated from `docs/schemas/openapi-hub.json` (`make schemas`).
 */

import createClient from "openapi-fetch";

import { API_BASE, ApiError, BASE_URL } from "./client";
import type { components, paths } from "./hub-schema";

export type HubSchemas = components["schemas"];
export type CoverageRow = HubSchemas["CoverageRowOut"];
export type Changeset = HubSchemas["ChangesetOut"];
export type Check = HubSchemas["CheckOut"];
export type Job = HubSchemas["JobOut"];
export type StudyArea = HubSchemas["StudyAreaOut"];

export const hubApi = createClient<paths>({
  baseUrl: BASE_URL,
  credentials: "same-origin",
  fetch: (request: Request) => globalThis.fetch(request),
});

/** Address of a hub download (template, export, report, package archive). */
export function hubUrl(path: string, params: Record<string, string> = {}): string {
  const query = new URLSearchParams(params).toString();
  return `${API_BASE}${path}${query ? `?${query}` : ""}`;
}

/** POST a file as the raw request body with query parameters (sources, facility imports). */
export async function uploadFile<T>(
  path: "/hub/sources" | "/hub/facility-imports",
  params: Record<string, string>,
  file: Blob,
): Promise<T> {
  const response = await fetch(hubUrl(path, params), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
  });
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  if (!response.ok) {
    const detail =
      typeof body.detail === "string" ? body.detail : `HTTP ${String(response.status)}`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

/** Whether a job reached a final state. */
export function jobFinished(job: Job | null | undefined): boolean {
  return (
    job !== null && job !== undefined && ["succeeded", "failed", "cancelled"].includes(job.status)
  );
}
