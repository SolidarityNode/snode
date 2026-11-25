import { useT } from "../i18n/context";
import { COLOURS, NOT_REPORTED, scaleClasses, type ColourScale } from "../map/styles";
import { num } from "./labels";
import { Legend } from "./Legend";

interface Props {
  title: string;
  scale: ColourScale;
  /** Add "not reported" and edge-effect entries (results maps). */
  unitMarks?: boolean;
  /** Data-quality entries, shown only while the quality layer is on. */
  quality?: boolean;
  testId?: string;
}

/** Legend of a classed colour scale, with every class in words. */
export function ScaleLegend({ title, scale, unitMarks = true, quality = false, testId }: Props) {
  const { t, lang } = useT();
  const { breaks } = scale;
  const classes = scale.colours.slice(0, scaleClasses(scale)).map((colour, i) => ({
    colour,
    label:
      breaks.length === 0
        ? t("legend.no_values")
        : i === 0
          ? `≤ ${num(breaks[0], lang)}`
          : i >= breaks.length
            ? `> ${num(breaks[breaks.length - 1], lang)}`
            : `${num(breaks[i - 1], lang)} – ${num(breaks[i], lang)}`,
  }));
  return (
    <div data-testid={testId}>
      <Legend
        title={title}
        items={[
          ...classes,
          ...(unitMarks
            ? [
                { colour: NOT_REPORTED, dashed: true, label: t("legend.not_reported") },
                { colour: "#ffffff", outline: COLOURS.orange, label: t("legend.edge_effect") },
              ]
            : []),
          ...(quality
            ? [
                { pattern: "hatch" as const, label: t("legend.estimated") },
                { pattern: "dots" as const, label: t("legend.open_data") },
              ]
            : []),
        ]}
      />
    </div>
  );
}
