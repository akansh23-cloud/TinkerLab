"use client";
import { clampMargin, formatValue, statusColor } from "@/lib/charts";
import type { DecisionCell, DecisionRequirement } from "@/lib/decision";

/**
 * How much headroom each requirement has, as a signed percentage against its own threshold.
 *
 * Signed so positive always means "better than required", whichever way the comparator points.
 * That normalisation is what lets a ≥ 145 °C requirement and a ≤ 8.5 USD/kg requirement share one
 * axis without the reader mentally reversing the sign for half the rows.
 *
 * UNKNOWN is a hatched band across the whole track, never a zero-length bar. A zero-length bar sits
 * exactly on the threshold, which claims the candidate is marginal when the truth is that nobody
 * measured it. Keeping those two apart is the point of the whole evidence model.
 */
export function RequirementMargins({
  cells, requirements, title, maxRows = 14,
}: {
  cells: DecisionCell[];
  requirements: DecisionRequirement[];
  title?: string;
  maxRows?: number;
}) {
  const byKey = new Map(requirements.map((r) => [r.property_key, r]));
  const rows = cells.slice(0, maxRows);
  if (!rows.length) return <div className="empty">No requirements to compare.</div>;

  const rowH = 32;
  const W = 780;
  const labelW = 236;
  const trackW = W - labelW - 96;
  const midX = labelW + trackW / 2;
  const H = rows.length * rowH + 46;

  return (
    <div className="chart-frame" data-testid="requirement-margins">
      {title && <div className="chart-title">{title}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Requirement margin by property">
        <defs>
          <pattern id="unknownHatch" width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <rect width="7" height="7" fill="#fbf3dd" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="#e3cb92" strokeWidth="2.5" />
          </pattern>
        </defs>

        <line x1={midX} y1={20} x2={midX} y2={H - 22} stroke="#64706b" strokeWidth={1.5} />
        <text x={midX} y={13} fontSize="10.5" textAnchor="middle" fill="#64706b" fontWeight={800}
              letterSpacing="0.06em">THRESHOLD</text>
        <text x={labelW} y={H - 6} fontSize="10.5" fill="#8d2e2e">short of requirement</text>
        <text x={W - 96} y={H - 6} fontSize="10.5" textAnchor="end" fill="#2f7d5c">headroom</text>

        {rows.map((cell, i) => {
          const y = 26 + i * rowH;
          const requirement = byKey.get(cell.property_key);
          const hard = requirement?.hard_or_soft === "hard";
          const color = statusColor(cell.status);
          const margin = cell.margin_percent;

          return (
            <g key={`${cell.property_key}-${i}`}>
              <text x={0} y={y + 12} fontSize="12" fill="#18201d" fontWeight={hard ? 650 : 400}>
                {(requirement?.display_name ?? cell.property_key.replaceAll("_", " ")).slice(0, 30)}
              </text>
              <text x={0} y={y + 24} fontSize="9.5" fill="#8a8f96">
                {hard ? "HARD" : "soft"}
                {requirement?.target_value !== null && requirement?.target_value !== undefined
                  ? ` · ${requirement.comparator} ${formatValue(requirement.target_value)} ${requirement.target_unit ?? ""}`
                  : requirement?.target_boolean !== null && requirement?.target_boolean !== undefined
                    ? ` · must be ${requirement.target_boolean ? "yes" : "no"}`
                    : ""}
              </text>

              {cell.status === "UNKNOWN" && (
                <>
                  <rect x={labelW} y={y + 2} width={trackW} height={16} fill="url(#unknownHatch)" stroke="#ecdba8" />
                  <text x={labelW + trackW / 2} y={y + 14} fontSize="10.5" textAnchor="middle"
                        fill="#795514" fontWeight={700}>
                    NOT MEASURED — no margin exists
                  </text>
                </>
              )}

              {cell.status !== "UNKNOWN" && typeof margin === "number" && (() => {
                const { value, clipped } = clampMargin(margin);
                const half = (Math.abs(value) / 100) * (trackW / 2);
                const x = value >= 0 ? midX : midX - half;
                return (
                  <>
                    <rect x={x} y={y + 2} width={Math.max(half, 2)} height={16} fill={color} fillOpacity={0.85} />
                    <text x={value >= 0 ? midX + half + 8 : midX - half - 8} y={y + 14} fontSize="11"
                          textAnchor={value >= 0 ? "start" : "end"} fill={color} fontWeight={700}>
                      {value >= 0 ? "+" : ""}{Math.round(margin)}%{clipped ? " ▸" : ""}
                    </text>
                    <title>
                      {`${cell.property_key}\nObserved ${formatValue(cell.canonical_value ?? NaN)} ${cell.canonical_unit ?? ""}\nStatus ${cell.status} · origin ${cell.value_origin ?? "—"}`}
                    </title>
                  </>
                );
              })()}

              {cell.status !== "UNKNOWN" && typeof margin !== "number" && (
                <>
                  <rect x={labelW} y={y + 2} width={trackW} height={16} fill="#f3f6f4" stroke="#dce3df" />
                  <text x={labelW + trackW / 2} y={y + 14} fontSize="10.5" textAnchor="middle" fill="#64706b">
                    {cell.status} · a compliance gate has no percentage margin
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      {cells.length > maxRows && (
        <div className="muted">Showing {maxRows} of {cells.length} requirements.</div>
      )}
    </div>
  );
}

/**
 * Candidate against incumbent, per property, as a signed percentage change.
 *
 * Colour follows whether the change *helps*, not whether the number went up: a lower density and a
 * higher strength are both improvements, and colouring by sign alone would make half the chart read
 * backwards.
 */
export function PropertyDeltas({
  properties, maxRows = 12,
}: {
  properties: {
    property_key: string;
    display_name: string;
    baseline_value?: number;
    candidate_value?: number;
    percentage_delta?: number;
    canonical_unit?: string;
    value_origin?: string;
    direction?: string;
  }[];
  maxRows?: number;
}) {
  const usable = properties.filter((p) => typeof p.percentage_delta === "number").slice(0, maxRows);
  const missing = properties.length - usable.length;
  if (!usable.length) {
    return (
      <div className="empty">
        No property has a recorded value on both the incumbent and this candidate, so no change can be stated.
      </div>
    );
  }

  const rowH = 28;
  const W = 780;
  const labelW = 250;
  const trackW = W - labelW - 90;
  const midX = labelW + trackW / 2;
  const H = usable.length * rowH + 42;
  const cap = Math.max(20, ...usable.map((p) => Math.min(Math.abs(p.percentage_delta ?? 0), 200)));

  return (
    <div className="chart-frame" data-testid="property-deltas">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Candidate change against the incumbent, by property">
        <line x1={midX} y1={18} x2={midX} y2={H - 18} stroke="#64706b" strokeWidth={1.5} />
        <text x={midX} y={11} fontSize="10.5" textAnchor="middle" fill="#64706b" fontWeight={800}
              letterSpacing="0.06em">INCUMBENT</text>

        {usable.map((property, i) => {
          const y = 24 + i * rowH;
          const delta = property.percentage_delta ?? 0;
          const direction = property.direction ?? "neutral";
          const directional = direction === "higher_is_better" || direction === "lower_is_better";
          const improves = direction === "lower_is_better" ? delta < 0
            : direction === "higher_is_better" ? delta > 0
              : null;
          const color = !directional ? "#64706b" : improves ? "#2f7d5c" : "#8d2e2e";
          const half = (Math.min(Math.abs(delta), cap) / cap) * (trackW / 2);
          const x = delta >= 0 ? midX : midX - half;
          return (
            <g key={property.property_key}>
              <text x={0} y={y + 13} fontSize="12" fill="#18201d">{property.display_name.slice(0, 32)}</text>
              <rect x={x} y={y + 3} width={Math.max(half, 2)} height={15} fill={color} fillOpacity={0.85} />
              <text x={delta >= 0 ? midX + half + 7 : midX - half - 7} y={y + 15} fontSize="11"
                    textAnchor={delta >= 0 ? "start" : "end"} fill={color} fontWeight={700}>
                {delta >= 0 ? "+" : ""}{Math.round(delta)}%
              </text>
              <title>
                {`${property.display_name}\n${formatValue(property.baseline_value ?? NaN)} → ${formatValue(property.candidate_value ?? NaN)} ${property.canonical_unit ?? ""}\n${!directional ? "Change — application dependent" : improves ? "Improvement" : "Regression"}`}
              </title>
            </g>
          );
        })}
      </svg>
      <div className="muted">
        Green/red is used only when the property catalogue declares a universal better direction. Properties
        with neutral, target-band or application-dependent meaning are grey and reported only as changes.
        {missing > 0 && ` ${missing} propert${missing === 1 ? "y is" : "ies are"} absent because one side has no recorded value.`}
      </div>
    </div>
  );
}
