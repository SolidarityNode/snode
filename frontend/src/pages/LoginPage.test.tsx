import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { renderWithSession } from "../test/utils";
import { LoginPage } from "./LoginPage";

async function signIn(status: number) {
  renderWithSession(<LoginPage />, {
    session: {
      user: null,
      login: () => Promise.reject(new ApiError(status, "server text is not shown")),
    },
  });
  await userEvent.type(screen.getByLabelText("Username"), "someone");
  await userEvent.type(screen.getByLabelText("Password"), "a-password-here");
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  return screen.findByRole("alert");
}

describe("LoginPage", () => {
  it("shows one generic message for a wrong or unknown user", async () => {
    expect(await signIn(401)).toHaveTextContent("Wrong username or password.");
  });

  it("says to wait after too many failed attempts, without naming the account", async () => {
    const alert = await signIn(429);
    expect(alert).toHaveTextContent("Too many failed sign-in attempts. Wait a few minutes");
    expect(alert).not.toHaveTextContent("someone");
  });
});
