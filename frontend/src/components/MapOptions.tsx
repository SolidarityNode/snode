import { useT } from "../i18n/context";

export interface MapOptionsValue {
  uncertainty: boolean;
  quality: boolean;
}

/** Results-map toggles: the uncertainty map and the data-quality layer (both off by default). */
export function MapOptions({
  value,
  onChange,
}: {
  value: MapOptionsValue;
  onChange: (value: MapOptionsValue) => void;
}) {
  const { t } = useT();
  return (
    <fieldset className="selectors">
      <legend>{t("results.map_options")}</legend>
      <label>
        <input
          type="checkbox"
          checked={value.uncertainty}
          onChange={(e) => {
            onChange({ ...value, uncertainty: e.target.checked });
          }}
        />{" "}
        {t("results.show_uncertainty")}
      </label>
      <label>
        <input
          type="checkbox"
          checked={value.quality}
          onChange={(e) => {
            onChange({ ...value, quality: e.target.checked });
          }}
        />{" "}
        {t("results.show_quality")}
      </label>
    </fieldset>
  );
}
