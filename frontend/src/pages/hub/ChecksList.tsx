import type { Check } from "../../api/hub";
import { label } from "../../components/labels";
import { useT } from "../../i18n/context";
import { serverText } from "../../i18n/server";

const ORDER = ["error", "warning", "info"] as const;

/** Checks of a processing record or entries of a validation report, errors first, translated. */
export function ChecksList({ checks, testId }: { checks: Check[]; testId?: string }) {
  const { t } = useT();
  if (checks.length === 0) return <p>{t("hub.checks.none")}</p>;
  return (
    <div data-testid={testId}>
      {ORDER.map((severity) => {
        const items = checks.filter((c) => c.severity === severity);
        if (items.length === 0) return null;
        return (
          <section key={severity} aria-label={label(t, "hub.severity", severity)}>
            <h4 className={`severity severity--${severity}`}>
              {label(t, "hub.severity", severity)} ({items.length})
            </h4>
            <ul>
              {items.map((c, i) => (
                <li key={`${c.code}-${String(i)}`} data-code={c.code}>
                  {serverText(t, c.message)}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
