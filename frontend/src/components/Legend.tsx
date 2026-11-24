interface Item {
  colour?: string;
  pattern?: "hatch" | "dots";
  outline?: string;
  dashed?: boolean;
  label: string;
}

/** Map legend: every symbol is also explained in words. */
export function Legend({ title, items }: { title: string; items: Item[] }) {
  return (
    <figure className="legend">
      <figcaption>{title}</figcaption>
      <ul>
        {items.map((item) => (
          <li key={item.label}>
            <svg width="22" height="14" aria-hidden="true">
              <rect
                x="1"
                y="1"
                width="20"
                height="12"
                fill={item.pattern ? `url(#sn-${item.pattern})` : (item.colour ?? "none")}
                stroke={item.outline ?? "#1d2433"}
                strokeWidth={item.outline ? 3 : 1}
                strokeDasharray={item.dashed ? "4 2" : undefined}
              />
            </svg>
            {item.label}
          </li>
        ))}
      </ul>
    </figure>
  );
}
