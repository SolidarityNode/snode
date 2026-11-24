import type { Schemas } from "../api/client";
import { useT } from "../i18n/context";
import { label } from "./labels";

import type { Selection } from "./selection";

interface Props {
  catalog: Schemas["CatalogOut"];
  indicators: Schemas["IndicatorOut"][];
  value: Selection;
  onChange: (value: Selection) => void;
}

/** Group, service and indicator selectors shared by the run and compare views. */
export function ResultSelectors({ catalog, indicators, value, onChange }: Props) {
  const { t } = useT();
  return (
    <fieldset className="selectors">
      <legend>{t("results.selectors")}</legend>
      <label>
        {t("results.group")}
        <select
          value={value.group}
          onChange={(e) => {
            onChange({ ...value, group: e.target.value });
          }}
        >
          {catalog.groups.map((g) => (
            <option key={g.group_id} value={g.group_id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("results.service")}
        <select
          value={value.service}
          onChange={(e) => {
            onChange({ ...value, service: e.target.value });
          }}
        >
          {catalog.services.map((s) => (
            <option key={s.service_id} value={s.service_id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("results.indicator")}
        <select
          value={value.indicator}
          onChange={(e) => {
            onChange({ ...value, indicator: e.target.value });
          }}
        >
          {indicators.map((i) => (
            <option key={i.id} value={i.id}>
              {label(t, "indicator", i.id)}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  );
}
