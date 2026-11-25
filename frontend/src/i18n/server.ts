/**
 * Translation of texts the backend and core produce (errors, reference problems, recorded-only
 * lines, changes per unit, run failures).
 *
 * The server writes every such text from an English template with a stable code
 * (`docs/schemas/messages.json`, copied to `src/api/messages.json` by `make schemas`). Here the
 * text is matched against those templates to recover the code and its parameters, and the
 * translation `server.<code>` is shown. Texts that match no template (for example technical
 * package diagnostics) are returned unchanged.
 */

import catalogue from "../api/messages.json";
import en from "./en.json";
import type { MessageKey, Translate } from "./context";
import { label } from "../components/labels";

interface Template {
  code: string;
  pattern: RegExp;
  names: string[];
  literal: number;
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Parameters that may contain spaces or punctuation. Every other parameter is an id, number or
 * version (no spaces, colons, semicolons, commas or brackets), which keeps general templates
 * such as `{service} {capacity_input} {before} -> {after}` from matching longer texts.
 */
const FREE_TEXT = new Set([
  "detail",
  "details",
  "times",
  "when",
  "time",
  "file",
  "username",
  "roles",
  "role",
]);

/** Compile `catalogue` into regular expressions, the most specific (most literal text) first. */
function compile(templates: Record<string, string>): Template[] {
  const out: Template[] = [];
  for (const [code, template] of Object.entries(templates)) {
    const names: string[] = [];
    let source = "";
    let literal = 0;
    let last = 0;
    for (const match of template.matchAll(/\{(\w+)(?::[^}]*)?\}/g)) {
      const text = template.slice(last, match.index);
      source += escape(text);
      literal += text.length;
      const name = String(match[1]);
      source += FREE_TEXT.has(name) ? "(.+?)" : "([^\\s:;,()]+)";
      names.push(name);
      last = match.index + match[0].length;
    }
    const tail = template.slice(last);
    source += escape(tail);
    literal += tail.length;
    out.push({ code, pattern: new RegExp(`^${source}$`, "s"), names, literal });
  }
  return out.sort((a, b) => b.literal - a.literal || a.code.localeCompare(b.code));
}

const TEMPLATES = compile(catalogue);

/** Parameters that are themselves server texts (or lists of them, with their separator). */
const NESTED: Record<string, string | null> = { detail: null, details: "; ", times: ", " };

/** Parameters whose values are ids with a translated label. */
const LABELLED: Record<string, string> = {
  mode: "mode",
  capacity_input: "attr",
  quantity: "quantity",
};

/** Return the code and parameters of a server text, or `null` if it matches no template. */
export function parseServerText(
  text: string,
): { code: string; params: Record<string, string> } | null {
  for (const template of TEMPLATES) {
    const match = template.pattern.exec(text);
    if (match) {
      const params: Record<string, string> = {};
      template.names.forEach((name, i) => {
        params[name] = match[i + 1] ?? "";
      });
      return { code: template.code, params };
    }
  }
  return null;
}

/** Translate a server text into the current language; unknown texts are returned unchanged. */
export function serverText(t: Translate, text: string): string {
  const parsed = parseServerText(text);
  if (!parsed) return text;
  const key = `server.${parsed.code}`;
  if (!(key in en)) return text;
  const vars: Record<string, string> = {};
  for (const [name, value] of Object.entries(parsed.params)) {
    if (name in NESTED) {
      const separator = NESTED[name];
      vars[name] = separator
        ? value
            .split(separator)
            .map((part) => serverText(t, part))
            .join(separator)
        : serverText(t, value);
    } else if (name in LABELLED) {
      vars[name] = label(t, LABELLED[name] ?? name, value);
    } else {
      vars[name] = value;
    }
  }
  return t(key as MessageKey, vars);
}
