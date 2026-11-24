import { describe, expect, it } from "vitest";

import el from "./el.json";
import en from "./en.json";

describe("translation catalogues", () => {
  it("have the same keys in English and Greek", () => {
    expect(Object.keys(el).sort()).toEqual(Object.keys(en).sort());
  });

  it("have no empty messages and keep the same placeholders", () => {
    for (const [key, text] of Object.entries(en)) {
      const greek = (el as Record<string, string>)[key] ?? "";
      expect(text, key).not.toBe("");
      expect(greek, key).not.toBe("");
      const vars = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
      expect(vars(greek), key).toEqual(vars(text));
    }
  });
});
