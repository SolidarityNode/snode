import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithSession, stubApi } from "../../test/utils";
import { Layout } from "../../components/Layout";
import { ChangesetView } from "./ChangesetView";
import { HubCoveragePage } from "./HubCoveragePage";
import { HubStudyAreasPage } from "./HubStudyAreasPage";

const HUB_CONFIG = {
  deployment_mode: "hub" as const,
  basemap: "blank" as const,
  app_env: "test",
  version: "0.1.0",
  git_commit: "abc",
  diagnostic_label: "Diagnostic model: not a research result",
  docs_url: "https://solidaritynode.github.io/snode/dev/",
};
const ADMIN = { id: 1, username: "admin", role: "admin" as const, active: true };
const cell = (status: string, version = "-") => ({ status, version, updated_at: null });

function row(id: string, status: string, facilities: string) {
  return {
    municipality_id: id,
    name: `Municipality ${id}`,
    status,
    onboarded: status !== "not_started",
    layers: {
      boundaries: cell(status === "not_started" ? "missing" : "open_data", "2026-11"),
      spatial_units: cell("open_data", "2026-11"),
      population: cell("open_data", "2026-11"),
      network: cell("open_data", "2026-11"),
      facilities: cell(facilities, "changeset 1"),
      transit: cell("missing"),
      susceptibility: cell("missing"),
    },
  };
}

describe("hub coverage matrix", () => {
  it("shows every municipality and layer with its status, and filters onboarded ones", async () => {
    let requests = 0;
    const { calls } = stubApi({
      "GET /hub/coverage": () =>
        ++requests > 1
          ? [row("M-A", "facilities_in_progress", "verified_by_municipality")]
          : [
              row("M-A", "facilities_in_progress", "verified_by_municipality"),
              row("M-D", "not_started", "missing"),
            ],
    });
    renderWithSession(<HubCoveragePage />, { session: { config: HUB_CONFIG, user: ADMIN } });
    const table = await screen.findByRole("table", { name: "Municipalities × layers" });
    const a = within(table).getByRole("row", { name: /M-A/ });
    expect(within(a).getByText("verified by the municipality")).toBeInTheDocument();
    expect(within(a).getAllByText("missing")).toHaveLength(2); // transit, susceptibility
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    await userEvent.selectOptions(screen.getByLabelText("Show"), "onboarded");
    await waitFor(() => {
      expect(within(table).getAllByRole("row")).toHaveLength(2);
    });
    expect(within(table).getByRole("row", { name: /M-A/ })).toHaveTextContent(
      "version changeset 1",
    );
    expect(calls.filter((c) => c.path === "/hub/coverage")).toHaveLength(2);
  });
});

const CHANGESET = {
  id: 7,
  kind: "import" as const,
  municipality_id: "M-A",
  status: "pending" as const,
  source: "Register",
  comment: "",
  file_name: "only-f1.csv",
  complete_list: true,
  is_correction: false,
  created_at: "2026-11-26T10:00:00Z",
  decided_at: null,
  created_by_name: "analyst",
  decided_by_name: null,
  summary: { add: 0, update: 1, close: 2 },
  errors: 0,
  licence: "CC-BY-4.0",
  attribution: "Register",
  file_sha256: "a".repeat(64),
  decision_comment: "",
  record_id: null,
  report: {
    entries: [
      {
        code: "hub.import.personal_column",
        severity: "warning",
        message:
          "column contact_person looks like personal data and was dropped (facilities are organisations, not people)",
        params: { column: "contact_person" },
      },
    ],
  },
  items: [
    {
      item_no: 1,
      action: "update" as const,
      facility_id: "HF-000001",
      label: "Community centre 1",
      rows: [2, 3],
      before: { services: { "S-SD": { throughput: 100 } } },
      after: { services: { "S-SD": { throughput: 90 } } },
      fields: ["services.S-SD.throughput"],
    },
    {
      item_no: 2,
      action: "close" as const,
      facility_id: "HF-000002",
      label: "Desk 2",
      rows: [],
      before: {},
      after: null,
      fields: [],
    },
  ],
};

describe("changeset preview", () => {
  it("shows the translated report and the field-level diff, and asks for the closure count", async () => {
    let approved: unknown = null;
    stubApi({
      "POST /hub/changesets/7/approve": (_url, init) => {
        approved = JSON.parse(init.body ?? "{}");
        return { ...CHANGESET, status: "approved", decided_by_name: "admin" };
      },
    });
    renderWithSession(<ChangesetView changeset={CHANGESET} onChange={() => undefined} />, {
      session: { config: HUB_CONFIG, user: ADMIN },
    });
    expect(screen.getByTestId("validation-report")).toHaveTextContent(
      "Column contact_person looks like personal data and was dropped",
    );
    const preview = screen.getByTestId("changeset-preview");
    expect(preview).toHaveTextContent("services.S-SD.throughput: 100 → 90");
    expect(preview).toHaveTextContent("closed (kept with an end date, never deleted)");
    await userEvent.type(
      screen.getByLabelText(/Type 2 to confirm that 2 facilities of M-A will be closed/),
      "2",
    );
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(approved).toEqual({ comment: "", confirm_close: 2 });
  });

  it("is shown in Greek with the server texts translated", () => {
    localStorage.setItem("sn-lang", "el");
    stubApi({});
    renderWithSession(<ChangesetView changeset={CHANGESET} onChange={() => undefined} />, {
      session: { config: HUB_CONFIG, user: ADMIN },
    });
    expect(screen.getByTestId("validation-report")).toHaveTextContent(
      "Η στήλη contact_person μοιάζει με προσωπικά δεδομένα και αφαιρέθηκε",
    );
    expect(screen.getByRole("button", { name: "Έγκριση" })).toBeInTheDocument();
    localStorage.removeItem("sn-lang");
  });
});

describe("propagation list", () => {
  it("lists study areas with an update available and offers to publish the next version", async () => {
    stubApi({
      "GET /hub/study-areas": () => [
        {
          id: "study-area-a",
          name: "Study area A",
          core_municipalities: ["M-A"],
          buffer_rule: "whole_neighbouring_municipalities",
          buffer_distance_m: null,
          buffer_municipalities: ["M-B", "M-C"],
          last_version: "1.0.0",
          update_available: true,
          pending: {
            last: { version: "1.0.0" },
            features: { facilities: { added: ["HF-000004"], changed: [], closed: [] } },
            coverage: [],
            changed: true,
            changelog: "facilities added: HF-000004",
            bump: "minor",
            next_version: "1.1.0",
          },
          packages: [
            {
              id: 1,
              version: "1.0.0",
              status: "published",
              bump: "initial",
              created: "2026-11-26",
              published_at: "2026-11-26T10:00:00Z",
              archive_sha256: "b".repeat(64),
              bytes: 1000,
              error: null,
              job_id: null,
              requested_at: "2026-11-26T10:00:00Z",
            },
          ],
        },
      ],
      "GET /hub/coverage": () => [],
    });
    renderWithSession(<HubStudyAreasPage />, { session: { config: HUB_CONFIG, user: ADMIN } });
    const list = await screen.findByTestId("propagation-list");
    expect(list).toHaveTextContent("study-area-a: 1.0.0 → 1.1.0");
    expect(list).toHaveTextContent("facilities added: HF-000004");
    expect(screen.getByRole("button", { name: "Publish 1.1.0" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download 1.0.0 (.zip)" })).toHaveAttribute(
      "href",
      "/api/hub/study-areas/study-area-a/packages/1.0.0/download",
    );
  });
});

describe("footer", () => {
  it("links to the user guide of the running version, in the UI language", () => {
    stubApi({ "GET /version": () => ({ version: "0.1.0", git_commit: "abc", app_env: "test" }) });
    renderWithSession(<Layout />, { session: { config: HUB_CONFIG, user: ADMIN } });
    expect(screen.getByTestId("user-guide")).toHaveAttribute(
      "href",
      "https://solidaritynode.github.io/snode/dev/",
    );
    expect(screen.getByRole("link", { name: "Onboarding" })).toBeInTheDocument();
    expect(screen.queryByTestId("data-version")).not.toBeInTheDocument();
  });
});
