/**
 * SVG fill patterns used by map styles (referenced as `url(#sn-hatch)` and `url(#sn-dots)`):
 * hatching marks `estimated` quality, dots mark `open_data` quality.
 */
export function MapPatterns() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <pattern
          id="sn-hatch"
          width="8"
          height="8"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line x1="0" y1="0" x2="0" y2="8" stroke="#1d2433" strokeWidth="2" />
        </pattern>
        <pattern id="sn-dots" width="7" height="7" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="#1d2433" />
        </pattern>
      </defs>
    </svg>
  );
}
