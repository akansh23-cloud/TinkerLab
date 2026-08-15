/**
 * Chart primitives.
 *
 * Hand-rolled rather than pulled from a charting library, for three reasons that matter here:
 * the bundle stays small, the output is deterministic and diffable, and — most importantly —
 * nothing in a general-purpose library knows that UNKNOWN is a real answer that must be drawn
 * differently from zero. Every helper below is pure and unit-tested.
 */

export type Scale = (value: number) => number;

/** Linear scale from a data domain to a pixel range. */
export function linearScale(min: number, max: number, from: number, to: number): Scale {
  const span = max - min || 1;
  return (value) => from + ((value - min) / span) * (to - from);
}

/**
 * Logarithmic scale. Engineering properties span orders of magnitude — polymer and ceramic moduli
 * differ by ~10^3 — so a linear axis collapses every polymer into one pixel column.
 * Non-positive input returns the range start rather than NaN, but callers are expected to have
 * excluded such values already; a log axis genuinely cannot represent them.
 */
export function logScale(min: number, max: number, from: number, to: number): Scale {
  const lo = Math.log10(Math.max(min, Number.MIN_VALUE));
  const hi = Math.log10(Math.max(max, Number.MIN_VALUE));
  const span = hi - lo || 1;
  return (value) => (value <= 0 ? from : from + ((Math.log10(value) - lo) / span) * (to - from));
}

/** Decade ticks (1, 10, 100…) plus 2× and 5× minors when the range is narrow enough to need them. */
export function logTicks(min: number, max: number): { value: number; major: boolean }[] {
  if (!(min > 0) || !(max > 0) || max < min) return [];
  const lo = Math.floor(Math.log10(min));
  const hi = Math.ceil(Math.log10(max));
  const decades = hi - lo;
  const minors = decades <= 3 ? [2, 5] : [];
  const ticks: { value: number; major: boolean }[] = [];
  for (let exp = lo; exp <= hi; exp += 1) {
    const base = Math.pow(10, exp);
    if (base >= min && base <= max) ticks.push({ value: base, major: true });
    for (const m of minors) {
      const value = base * m;
      if (value >= min && value <= max) ticks.push({ value, major: false });
    }
  }
  return ticks.sort((a, b) => a.value - b.value);
}

export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const raw = (max - min) / Math.max(count, 1);
  const magnitude = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
  const normalized = raw / magnitude;
  const step = (normalized >= 5 ? 10 : normalized >= 2 ? 5 : normalized >= 1 ? 2 : 1) * magnitude;
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/** Compact engineering formatting. 1360 → "1.36k", 0.00042 → "420µ". */
export function formatValue(value: number, precision = 3): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs >= 1e9) return `${Number((value / 1e9).toPrecision(precision))}G`;
  if (abs >= 1e6) return `${Number((value / 1e6).toPrecision(precision))}M`;
  if (abs >= 1e3) return `${Number((value / 1e3).toPrecision(precision))}k`;
  if (abs >= 1) return String(Number(value.toPrecision(precision)));
  if (abs >= 1e-3) return String(Number(value.toPrecision(precision)));
  if (abs >= 1e-6) return `${Number((value * 1e3).toPrecision(precision))}m`;
  return `${Number((value * 1e6).toPrecision(precision))}µ`;
}

/**
 * Family palette. Chosen to stay distinguishable under the common forms of colour-vision
 * deficiency, but colour is never the only channel: every family also carries a distinct marker
 * shape, and every chart in this app repeats the meaning in text.
 */
export const FAMILY_COLORS: Record<string, string> = {
  polymer: "#1e5b48",
  alloy: "#8a5a1f",
  ceramic: "#5b3f86",
  composite: "#1d5f7a",
  coating: "#7a1d4e",
  adhesive: "#4a6320",
  crystalline_inorganic: "#5a5f6b",
  unknown: "#8a8f96",
};

export type MarkerShape = "circle" | "square" | "triangle" | "diamond" | "cross" | "pentagon" | "hexagon" | "x";

export const FAMILY_SHAPES: Record<string, MarkerShape> = {
  polymer: "circle",
  alloy: "square",
  ceramic: "triangle",
  composite: "diamond",
  coating: "cross",
  adhesive: "pentagon",
  crystalline_inorganic: "hexagon",
  unknown: "x",
};

export function familyColor(family: string): string {
  return FAMILY_COLORS[family] ?? FAMILY_COLORS.unknown;
}

export function familyShape(family: string): MarkerShape {
  return FAMILY_SHAPES[family] ?? "circle";
}

/** SVG path for a marker centred at (cx, cy). Shape carries family, so colour never has to. */
export function markerPath(shape: MarkerShape, cx: number, cy: number, r: number): string {
  switch (shape) {
    case "square":
      return `M${cx - r},${cy - r} h${r * 2} v${r * 2} h${-r * 2} Z`;
    case "triangle":
      return `M${cx},${cy - r * 1.15} L${cx + r * 1.1},${cy + r * 0.85} L${cx - r * 1.1},${cy + r * 0.85} Z`;
    case "diamond":
      return `M${cx},${cy - r * 1.25} L${cx + r * 1.15},${cy} L${cx},${cy + r * 1.25} L${cx - r * 1.15},${cy} Z`;
    case "cross": {
      const a = r * 0.42;
      return `M${cx - a},${cy - r} h${a * 2} v${r - a} h${r - a} v${a * 2} h${-(r - a)} v${r - a} h${-a * 2} v${-(r - a)} h${-(r - a)} v${-a * 2} h${r - a} Z`;
    }
    case "pentagon": {
      const pts = Array.from({ length: 5 }, (_, i) => {
        const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
        return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
      });
      return `M${pts.map((p) => `${p[0]},${p[1]}`).join(" L")} Z`;
    }
    case "hexagon": {
      const pts = Array.from({ length: 6 }, (_, i) => {
        const a = (i * Math.PI) / 3;
        return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
      });
      return `M${pts.map((p) => `${p[0]},${p[1]}`).join(" L")} Z`;
    }
    case "x": {
      const a = r * 0.32;
      return `M${cx - r},${cy - r + a} L${cx - r + a},${cy - r} L${cx},${cy - a} L${cx + r - a},${cy - r} L${cx + r},${cy - r + a} L${cx + a},${cy} L${cx + r},${cy + r - a} L${cx + r - a},${cy + r} L${cx},${cy + a} L${cx - r + a},${cy + r} L${cx - r},${cy + r - a} L${cx - a},${cy} Z`;
    }
    default:
      return `M${cx},${cy} m${-r},0 a${r},${r} 0 1,0 ${r * 2},0 a${r},${r} 0 1,0 ${-r * 2},0`;
  }
}

/**
 * Origin styling. A measured value and a model prediction must never look the same — that
 * distinction is the platform's central claim, and a chart that flattens it undoes the whole
 * evidence model in one image.
 */
export const ORIGIN_STYLE: Record<string, { label: string; opacity: number; dashed: boolean }> = {
  measured: { label: "Measured", opacity: 1, dashed: false },
  supplier: { label: "Supplier declared", opacity: 0.9, dashed: false },
  literature: { label: "Literature / handbook", opacity: 0.72, dashed: true },
  simulation: { label: "Simulated", opacity: 0.7, dashed: true },
  prediction: { label: "Model prediction", opacity: 0.6, dashed: true },
  declared: { label: "Declared", opacity: 0.6, dashed: true },
  unknown: { label: "Unknown", opacity: 0.35, dashed: true },
  accredited_laboratory: { label: "Accredited laboratory", opacity: 1, dashed: false },
  internal_measurement: { label: "Internal measurement", opacity: 0.96, dashed: false },
  supplier_declared: { label: "Supplier datasheet", opacity: 0.88, dashed: false },
  peer_reviewed: { label: "Published literature", opacity: 0.76, dashed: true },
  physics_simulation: { label: "Physics simulation", opacity: 0.7, dashed: true },
  computed_database: { label: "Computed database", opacity: 0.66, dashed: true },
  model_prediction: { label: "Model prediction", opacity: 0.58, dashed: true },
  handbook_typical: { label: "Reference handbook", opacity: 0.52, dashed: true },
  engineering_estimate: { label: "Engineering estimate", opacity: 0.43, dashed: true },
  none: { label: "Missing", opacity: 0.25, dashed: true },
};

export function originStyle(origin: string) {
  return ORIGIN_STYLE[origin] ?? ORIGIN_STYLE.unknown;
}

export const STATUS_COLORS: Record<string, string> = {
  PASS: "#2f7d5c",
  pass: "#2f7d5c",
  FAIL: "#8d2e2e",
  fail: "#8d2e2e",
  UNKNOWN: "#b8892a",
  unknown: "#b8892a",
  conflicting: "#7a1d4e",
  inconclusive: "#5a5f6b",
  not_comparable: "#5a5f6b",
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#8a8f96";
}

/**
 * Percentage margin of an observed value against a threshold, signed so positive always means
 * "better than required" regardless of comparator direction. Returns null when the comparison is
 * not defined — an UNKNOWN has no margin, and rendering it as 0% would read as "exactly at the
 * limit", which is a specific and misleading claim.
 */
export function requirementMargin(
  observed: number | null | undefined,
  target: number | null | undefined,
  comparator: string,
): number | null {
  if (observed === null || observed === undefined || target === null || target === undefined) return null;
  if (!Number.isFinite(observed) || !Number.isFinite(target) || target === 0) return null;
  if (comparator === ">=" || comparator === ">") return ((observed - target) / Math.abs(target)) * 100;
  if (comparator === "<=" || comparator === "<") return ((target - observed) / Math.abs(target)) * 100;
  return null;
}

/** Clamp a margin into the drawable band while remembering that it was clipped. */
export function clampMargin(margin: number, limit = 100): { value: number; clipped: boolean } {
  if (margin > limit) return { value: limit, clipped: true };
  if (margin < -limit) return { value: -limit, clipped: true };
  return { value: margin, clipped: false };
}
