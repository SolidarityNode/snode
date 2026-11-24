import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n/I18nProvider";
import { RunStatus } from "./RunStatus";

function renderStatus(run: Parameters<typeof RunStatus>[0]["run"], onCancel = vi.fn()) {
  render(
    <I18nProvider>
      <RunStatus run={run} onCancel={onCancel} />
    </I18nProvider>,
  );
  return onCancel;
}

describe("RunStatus", () => {
  it("shows progress and a cancel button while running", async () => {
    const onCancel = renderStatus({
      status: "running",
      progress: 40,
      error: null,
      can_cancel: true,
    });
    expect(screen.getByTestId("run-status")).toHaveTextContent("running");
    expect(screen.getByRole("progressbar", { name: "Run progress" })).toHaveAttribute(
      "value",
      "40",
    );
    expect(screen.getByText("40 % done")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("hides cancel when the user may not cancel", () => {
    renderStatus({ status: "queued", progress: 0, error: null, can_cancel: false });
    expect(screen.getByTestId("run-status")).toHaveTextContent("queued");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the error of a failed run and no progress bar", () => {
    renderStatus({
      status: "failed",
      progress: 30,
      error: "Interrupted: the worker (worker) stopped while this run was running.",
      can_cancel: false,
    });
    expect(screen.getByRole("alert")).toHaveTextContent("The run failed: Interrupted");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows succeeded without progress or cancel", () => {
    renderStatus({ status: "succeeded", progress: 100, error: null, can_cancel: false });
    expect(screen.getByTestId("run-status")).toHaveTextContent("succeeded");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
