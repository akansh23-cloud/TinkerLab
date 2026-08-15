"use client";
import { useMemo, useState } from "react";
import {
  familyColor, familyShape, formatValue, logScale, logTicks, markerPath, originStyle,
} from "@/lib/charts";

export type PropertyPoint = {
  material_id: string;
  display_name: string;
  material_family: string;
  is_seed_data: boolean;
  x: number;
  y: number;
  x_origin: string;
  y_origin: string;
  x_provenance?: string;
  y_provenance?: string;
  weakest_origin?: string;
  x_confidence: number | null;
  y_confidence: number | null;
  highlighted: boolean;
};

export type AxisMeta = {
  key: string;
  display_name: string;
  canonical_unit: string | null;
  direction: string;
  test_standard: string | null;
  why_it_matters: string | null;
};

export type MaterialIndexMeta = {
  key: string;
  label: string;
  design_case: string;
  exponent: number;
  log_slope: number;
  maximise: boolean;
};

const W = 860;
const H = 560;
const PAD = { left: 78, right: 210, top: 26, bottom: 66 };

/**
 * The Ashby chart: two properties on log axes, materials by family, and material-index guide lines.
 *
 * The guide lines are the point. Ranking on raw strength answers the wrong question — a tie rod is
 * selected on σ/ρ, a beam in bending on σ^⅔/ρ, a panel on σ^½/ρ, and those lines have different
 * slopes, so the winner changes with the loading mode. Drawing a scatter without them would look
 * like an Ashby chart while omitting the reason anyone draws one.
 *
 * The line is positioned by dragging it up until it just touches the best material for that index,
 * which is exactly how the construction is used on paper: everything above and to the left of the
 * line beats everything below and to the right, for that design case.
 */
export function AshbyChart({
  points, xAxis, yAxis, indices, activeIndexKey, onSelectIndex, requirementX, requirementY,
}: {
  points: PropertyPoint[];
  xAxis: AxisMeta;
  yAxis: AxisMeta;
  indices: MaterialIndexMeta[];
  activeIndexKey?: string;
  onSelectIndex?: (key: string) => void;
  requirementX?: { min?: number; max?: number };
  requirementY?: { min?: number; max?: number };
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [hiddenFamilies, setHiddenFamilies] = useState<string[]>([]);

  const visible = points.filter((p) => !hiddenFamilies.includes(p.material_family));

  const bounds = useMemo(() => {
    if (!visible.length) return null;
    const xs = visible.map((p) => p.x);
    const ys = visible.map((p) => p.y);
    // A tenth of a decade of padding keeps extreme points off the axis line without distorting
    // the log spacing.
    const pad = (lo: number, hi: number): [number, number] => [
      Math.pow(10, Math.log10(lo) - 0.12),
      Math.pow(10, Math.log10(hi) + 0.12),
    ];
    const [x0, x1] = pad(Math.min(...xs), Math.max(...xs));
    const [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
    return { x0, x1, y0, y1 };
  }, [visible]);

  const families = useMemo(
    () => Array.from(new Set(points.map((p) => p.material_family))).sort(),
    [points],
  );

  const activeIndex = indices.find((i) => i.key === activeIndexKey);

  // Place the guide line through the material that maximises the index, so it reads as a selection
  // frontier rather than an arbitrary decoration.
  const guide = useMemo(() => {
    if (!activeIndex || !visible.length) return null;
    let best = visible[0];
    let bestValue = -Infinity;
    for (const point of visible) {
      const value = Math.pow(point.y, activeIndex.exponent) / point.x;
      if (value > bestValue) { bestValue = value; best = point; }
    }
    const slope = activeIndex.log_slope;
    const logC = Math.log10(best.y) - slope * Math.log10(best.x);
    const yAt = (x: number) => Math.pow(10, slope * Math.log10(x) + logC);
    return { best, bestValue, yAt };
  }, [activeIndex, visible]);

  if (!points.length) {
    return (
      <div className="empty">
        No material has a recorded value for both {xAxis.display_name} and {yAxis.display_name}.
        Record those properties, or pick another axis pair.
      </div>
    );
  }
  if (!bounds) {
    return <div className="empty">Every family is hidden. Re-enable one in the legend to plot again.</div>;
  }

  const sx = logScale(bounds.x0, bounds.x1, PAD.left, W - PAD.right);
  const sy = logScale(bounds.y0, bounds.y1, H - PAD.bottom, PAD.top);
  const xTicks = logTicks(bounds.x0, bounds.x1);
  const yTicks = logTicks(bounds.y0, bounds.y1);

  const hoveredPoint = visible.find((p) => p.material_id === hovered);

  return (
    <div className="chart-frame" data-testid="ashby-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Material property chart: ${yAxis.display_name} against ${xAxis.display_name} on logarithmic axes`}>
        {/* grid */}
        {xTicks.map((t) => (
          <line key={`gx-${t.value}`} x1={sx(t.value)} y1={PAD.top} x2={sx(t.value)} y2={H - PAD.bottom}
                stroke="#dce3df" strokeWidth={t.major ? 1 : 0.5} strokeDasharray={t.major ? undefined : "2 3"} />
        ))}
        {yTicks.map((t) => (
          <line key={`gy-${t.value}`} x1={PAD.left} y1={sy(t.value)} x2={W - PAD.right} y2={sy(t.value)}
                stroke="#dce3df" strokeWidth={t.major ? 1 : 0.5} strokeDasharray={t.major ? undefined : "2 3"} />
        ))}

        {/* requirement window: the region that satisfies the study's thresholds */}
        {(requirementX || requirementY) && (
          <g>
            <rect
              x={sx(requirementX?.min ?? bounds.x0)}
              y={sy(requirementY?.max ?? bounds.y1)}
              width={Math.max(0, sx(requirementX?.max ?? bounds.x1) - sx(requirementX?.min ?? bounds.x0))}
              height={Math.max(0, sy(requirementY?.min ?? bounds.y0) - sy(requirementY?.max ?? bounds.y1))}
              fill="#1e5b48" opacity={0.07} stroke="#1e5b48" strokeOpacity={0.35} strokeDasharray="5 4"
            />
            <text x={sx(requirementX?.min ?? bounds.x0) + 8} y={sy(requirementY?.max ?? bounds.y1) + 16}
                  fontSize="11" fill="#1e5b48" fontWeight={700}>
              Meets both thresholds
            </text>
          </g>
        )}

        {/* material index guide line */}
        {guide && activeIndex && (
          <g>
            <line
              x1={sx(bounds.x0)} y1={sy(guide.yAt(bounds.x0))}
              x2={sx(bounds.x1)} y2={sy(guide.yAt(bounds.x1))}
              stroke="#8a5a1f" strokeWidth={2} strokeDasharray="7 5"
            />
            <text x={PAD.left + 10} y={Math.max(PAD.top + 14, sy(guide.yAt(bounds.x0)) - 8)}
                  fontSize="12" fill="#8a5a1f" fontWeight={750}>
              {activeIndex.label} — best: {guide.best.display_name}
            </text>
          </g>
        )}

        {/* axes */}
        <line x1={PAD.left} y1={H - PAD.bottom} x2={W - PAD.right} y2={H - PAD.bottom} stroke="#64706b" />
        <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={H - PAD.bottom} stroke="#64706b" />
        {xTicks.filter((t) => t.major).map((t) => (
          <text key={`tx-${t.value}`} x={sx(t.value)} y={H - PAD.bottom + 17} fontSize="11"
                textAnchor="middle" fill="#64706b">{formatValue(t.value)}</text>
        ))}
        {yTicks.filter((t) => t.major).map((t) => (
          <text key={`ty-${t.value}`} x={PAD.left - 8} y={sy(t.value) + 4} fontSize="11"
                textAnchor="end" fill="#64706b">{formatValue(t.value)}</text>
        ))}
        <text x={(PAD.left + W - PAD.right) / 2} y={H - 22} fontSize="12.5" textAnchor="middle" fontWeight={650}>
          {xAxis.display_name}{xAxis.canonical_unit ? ` (${xAxis.canonical_unit})` : ""} · log scale
        </text>
        <text x={20} y={(PAD.top + H - PAD.bottom) / 2} fontSize="12.5" textAnchor="middle" fontWeight={650}
              transform={`rotate(-90 20 ${(PAD.top + H - PAD.bottom) / 2})`}>
          {yAxis.display_name}{yAxis.canonical_unit ? ` (${yAxis.canonical_unit})` : ""} · log scale
        </text>

        {/* points */}
        {visible.map((point) => {
          const color = familyColor(point.material_family);
          const shape = familyShape(point.material_family);
          // The backend resolves this with an explicit evidence-strength policy. Never infer
          // scientific weakness from string/alphabetical ordering in the browser.
          const weakest = point.weakest_origin ?? point.x_provenance ?? point.x_origin;
          const style = originStyle(weakest);
          const isActive = hovered === point.material_id || point.highlighted;
          const r = point.highlighted ? 9 : isActive ? 8 : 6;
          return (
            <g key={point.material_id}
               onMouseEnter={() => setHovered(point.material_id)}
               onMouseLeave={() => setHovered(null)}>
              {point.highlighted && (
                <circle cx={sx(point.x)} cy={sy(point.y)} r={15} fill="none" stroke={color}
                        strokeWidth={1.5} strokeDasharray="3 3" />
              )}
              <path d={markerPath(shape, sx(point.x), sy(point.y), r)} fill={color}
                    fillOpacity={style.opacity} stroke={isActive ? "#18201d" : color}
                    strokeWidth={isActive ? 1.5 : 0.8} strokeDasharray={style.dashed ? "3 2" : undefined} />
              <title>
                {`${point.display_name} · ${point.material_family}\n`}
                {`${xAxis.display_name}: ${formatValue(point.x)} ${xAxis.canonical_unit ?? ""} (${point.x_provenance ?? point.x_origin})\n`}
                {`${yAxis.display_name}: ${formatValue(point.y)} ${yAxis.canonical_unit ?? ""} (${point.y_provenance ?? point.y_origin})`}
              </title>
            </g>
          );
        })}

        {/* hovered label, drawn last so it is never occluded */}
        {hoveredPoint && (
          <text x={sx(hoveredPoint.x) + 12} y={sy(hoveredPoint.y) - 10} fontSize="12" fontWeight={700} fill="#18201d">
            {hoveredPoint.display_name}
          </text>
        )}

        {/* legend */}
        <g transform={`translate(${W - PAD.right + 16}, ${PAD.top + 4})`}>
          <text fontSize="11" fontWeight={800} fill="#64706b" letterSpacing="0.08em">FAMILY</text>
          {families.map((family, i) => {
            const hidden = hiddenFamilies.includes(family);
            return (
              <g key={family} transform={`translate(0, ${20 + i * 21})`} style={{ cursor: "pointer" }}
                 onClick={() =>
                   setHiddenFamilies(hidden
                     ? hiddenFamilies.filter((f) => f !== family)
                     : [...hiddenFamilies, family])}>
                <path d={markerPath(familyShape(family), 6, -4, 6)} fill={familyColor(family)}
                      fillOpacity={hidden ? 0.18 : 1} />
                <text x={20} y={0} fontSize="11.5" fill={hidden ? "#a9b4af" : "#18201d"}>
                  {family.replace("_", " ")}
                </text>
              </g>
            );
          })}
          <text y={40 + families.length * 21} fontSize="11" fontWeight={800} fill="#64706b" letterSpacing="0.08em">
            ORIGIN
          </text>
          {["internal_measurement", "supplier_declared", "peer_reviewed", "model_prediction"].map((origin, i) => (
            <g key={origin} transform={`translate(0, ${58 + families.length * 21 + i * 19})`}>
              <circle cx={6} cy={-4} r={5} fill="#5a5f6b" fillOpacity={originStyle(origin).opacity} />
              <text x={20} y={0} fontSize="11" fill="#64706b">{originStyle(origin).label}</text>
            </g>
          ))}
        </g>
      </svg>

      {indices.length > 0 && (
        <div className="chart-controls">
          <span className="kicker">Material index</span>
          <div className="chip-row">
            <button className={`chip ${!activeIndexKey ? "chip-active" : ""}`}
                    onClick={() => onSelectIndex?.("")}>
              None
            </button>
            {indices.map((index) => (
              <button key={index.key}
                      className={`chip ${activeIndexKey === index.key ? "chip-active" : ""}`}
                      title={index.design_case}
                      onClick={() => onSelectIndex?.(index.key)}>
                {index.label}
              </button>
            ))}
          </div>
          {activeIndex && <div className="muted" style={{ marginTop: 8 }}>{activeIndex.design_case}. Everything above and left of the line beats everything below and right of it, for this loading mode.</div>}
        </div>
      )}
    </div>
  );
}
