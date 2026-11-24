import { useT } from "../i18n/context";

/** Visible on every result produced by a diagnostic model (diagnostic-v0). */
export function DiagnosticBanner() {
  const { t } = useT();
  return (
    <div className="banner banner--diagnostic" role="note" data-testid="diagnostic-banner">
      <strong>{t("diagnostic.title")}</strong> {t("diagnostic.body")}
    </div>
  );
}
