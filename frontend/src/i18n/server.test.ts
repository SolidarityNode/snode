import { describe, expect, it } from "vitest";

import catalogue from "../api/messages.json";
import el from "./el.json";
import en from "./en.json";
import { format, type MessageKey, type Translate } from "./context";
import { parseServerText, serverText } from "./server";

const greek: Translate = (key: MessageKey, vars) =>
  format((el as Record<string, string>)[key] ?? key, vars);
const english: Translate = (key: MessageKey, vars) => format(en[key], vars);
const fields = (s: string) => [...s.matchAll(/\{(\w+)(?::[^}]*)?\}/g)].map((m) => m[1]).sort();

describe("server message catalogue", () => {
  it("has an English and a Greek text for every code, with the template's fields", () => {
    for (const [code, template] of Object.entries(catalogue)) {
      const key = `server.${code}`;
      expect(en, key).toHaveProperty([key]);
      expect(el, key).toHaveProperty([key]);
      expect(fields((en as Record<string, string>)[key] ?? ""), key).toEqual(fields(template));
      expect(fields((el as Record<string, string>)[key] ?? ""), key).toEqual(fields(template));
    }
  });

  it("recovers the code and parameters of a server text", () => {
    expect(parseServerText("edge E02: closed or missing in data 1.1.0")).toEqual({
      code: "scenario.edge_missing_in",
      params: { edge: "E02", version: "1.1.0" },
    });
    expect(parseServerText("edge E02: cannot be closed (closable = false)")?.code).toBe(
      "scenario.edge_not_closable",
    );
    expect(parseServerText("something the server never says")).toBeNull();
  });

  it("translates errors, nested texts and labelled ids", () => {
    expect(serverText(greek, "run not found")).toBe("Η εκτέλεση δεν βρέθηκε.");
    expect(serverText(english, "run not found")).toBe("Run not found.");
    expect(
      serverText(greek, "new edge E-NEW N-A1-N-A5 (car 2 min, walk 10 min) (recorded only)"),
    ).toBe("νέο τμήμα E-NEW N-A1-N-A5 (αυτοκίνητο 2 λεπτά, πεζή 10 λεπτά) (καταγράφεται μόνο)");
    expect(serverText(greek, "package.csv: unexpected column x")).toBe(
      "package.csv: unexpected column x",
    );
  });
});
