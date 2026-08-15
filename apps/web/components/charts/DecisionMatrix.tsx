"use client";
import { useState } from "react";
import { formatValue, statusColor } from "@/lib/charts";
import type { DecisionCandidate, DecisionRequirement } from "@/lib/decision";

const STATUS_GLYPH: Record<string, string> = {
  PASS: "✓", FAIL: "✕", UNKNOWN: "?", CONFLICTING: "!", INCONCLUSIVE: "~", NOT_COMPARABLE: "≠",
};

/**
 * Candidates against requirements, as a grid.
 *
 * Every cell carries a glyph as well as a colour. That is not decoration: roughly one man in twelve
 * cannot reliably separate the red and green used for FAIL and PASS, and this grid is the screen a
 * qualification decision gets argued from. Colour is the fast channel; the glyph is the reliable one.
 *
 * Hard requirements are drawn first and separated by a rule, because a single hard FAIL eliminates a
 * candidate no matter how well it scores on everything to its right.
 */
export function DecisionMatrix({
  candidates, requirements, onSelectCandidate, selectedCandidateId,
}: {
  candidates: DecisionCandidate[];
  requirements: DecisionRequirement[];
  onSelectCandidate?: (id: string) => void;
  selectedCandidateId?: string;
}) {
  const [hover, setHover] = useState<{ candidate: string; property: string } | null>(null);

  if (!candidates.length) {
    return (
      <div className="empty">
        No candidates yet. Generate them in the Candidate Lab, then this grid fills in.
      </div>
    );
  }
  if (!requirements.length) return <div className="empty">No requirements defined for this study.</div>;

  const hard = requirements.filter((r) => r.hard_or_soft === "hard");
  const soft = requirements.filter((r) => r.hard_or_soft !== "hard");
  const ordered = [...hard, ...soft];

  const cellW = 38;
  const cellH = 30;
  const nameW = 210;
  const headerH = 132;
  const W = nameW + ordered.length * cellW + 76;
  const H = headerH + candidates.length * cellH + 22;

  const hovered = hover
    ? candidates.find((c) => c.candidate_id === hover.candidate)?.cells.find((c) => c.property_key === hover.property)
    : null;

  return (
    <div className="chart-frame" data-testid="decision-matrix">
      <div className="chart-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 1100) }} role="img"
             aria-label="Decision matrix of candidates against requirements">
          {/* rotated requirement headers */}
          {ordered.map((requirement, c) => {
            const x = nameW + c * cellW + cellW / 2;
            return (
              <text key={requirement.property_key} x={x} y={headerH - 12} fontSize="11"
                    textAnchor="start" fill="#18201d"
                    fontWeight={requirement.hard_or_soft === "hard" ? 700 : 400}
                    transform={`rotate(-58 ${x} ${headerH - 12})`}>
                {(requirement.display_name ?? requirement.property_key).slice(0, 24)}
              </text>
            );
          })}
          {hard.length > 0 && hard.length < ordered.length && (
            <line x1={nameW + hard.length * cellW} y1={headerH - 6} x2={nameW + hard.length * cellW}
                  y2={H - 18} stroke="#64706b" strokeDasharray="4 3" />
          )}
          <text x={nameW} y={headerH - 2} fontSize="9.5" fill="#8d2e2e" fontWeight={800} letterSpacing="0.06em">
            {hard.length > 0 ? "HARD — CAN ELIMINATE" : ""}
          </text>
          {soft.length > 0 && (
            <text x={nameW + hard.length * cellW + 4} y={headerH - 2} fontSize="9.5" fill="#64706b"
                  fontWeight={800} letterSpacing="0.06em">SOFT — RANKS ONLY</text>
          )}

          {candidates.map((candidate, r) => {
            const y = headerH + r * cellH;
            const eliminated = (candidate.hard_failed ?? 0) > 0;
            const selected = candidate.candidate_id === selectedCandidateId;
            return (
              <g key={candidate.candidate_id}>
                {selected && (
                  <rect x={0} y={y} width={W} height={cellH} fill="#e9f3ef" />
                )}
                <text x={0} y={y + 19} fontSize="12" fill={eliminated ? "#8a8f96" : "#18201d"}
                      fontWeight={selected ? 700 : 400}
                      style={{ cursor: onSelectCandidate ? "pointer" : "default" }}
                      onClick={() => onSelectCandidate?.(candidate.candidate_id)}>
                  {eliminated ? "⊘ " : ""}{(candidate.display_name ?? "Candidate").slice(0, 26)}
                </text>

                {ordered.map((requirement, c) => {
                  const cell = candidate.cells.find((x) => x.property_key === requirement.property_key);
                  const status = cell?.status ?? "UNKNOWN";
                  const x = nameW + c * cellW;
                  const isHover = hover?.candidate === candidate.candidate_id
                    && hover?.property === requirement.property_key;
                  return (
                    <g key={requirement.property_key}
                       onMouseEnter={() => setHover({ candidate: candidate.candidate_id, property: requirement.property_key })}
                       onMouseLeave={() => setHover(null)}>
                      <rect x={x + 2} y={y + 3} width={cellW - 4} height={cellH - 6} rx={4}
                            fill={statusColor(status)}
                            fillOpacity={status === "UNKNOWN" ? 0.16 : 0.86}
                            stroke={isHover ? "#18201d" : "none"} strokeWidth={1.5} />
                      <text x={x + cellW / 2} y={y + 21} fontSize="13" textAnchor="middle"
                            fontWeight={800}
                            fill={status === "UNKNOWN" ? "#795514" : "white"}>
                        {STATUS_GLYPH[status] ?? "·"}
                      </text>
                      {cell?.conflict && (
                        <circle cx={x + cellW - 6} cy={y + 8} r={3} fill="#7a1d4e" />
                      )}
                      <title>
                        {`${candidate.display_name} · ${requirement.display_name}\n${status}`}
                        {cell?.canonical_value !== null && cell?.canonical_value !== undefined
                          ? `\nObserved ${formatValue(cell.canonical_value)} ${cell.canonical_unit ?? ""}`
                          : ""}
                        {cell?.unknown_reason ? `\n${cell.unknown_reason}` : ""}
                        {cell?.conflict ? "\nConflicting sources — not averaged" : ""}
                      </title>
                    </g>
                  );
                })}

                <text x={nameW + ordered.length * cellW + 10} y={y + 19} fontSize="11" fill="#64706b">
                  {Math.round((candidate.completeness ?? 0) * 100)}%
                </text>
              </g>
            );
          })}
          <text x={nameW + ordered.length * cellW + 10} y={headerH - 12} fontSize="9.5" fill="#64706b"
                fontWeight={800}>EVID.</text>
        </svg>
      </div>

      <div className="matrix-legend">
        {[["PASS", "meets it"], ["FAIL", "misses it"], ["UNKNOWN", "nobody measured it"]].map(([status, text]) => (
          <span key={status} className="legend-item">
            <span className="legend-swatch" style={{
              background: statusColor(status),
              opacity: status === "UNKNOWN" ? 0.3 : 0.86,
            }}>{STATUS_GLYPH[status]}</span>
            {status} — {text}
          </span>
        ))}
        <span className="legend-item"><span className="legend-dot" /> conflicting sources, shown not averaged</span>
        <span className="legend-item">⊘ marks a candidate eliminated by a hard requirement</span>
      </div>
      {hovered && (
        <div className="muted">
          {hovered.property_key}: {hovered.status}
          {hovered.value_origin ? ` · value from ${hovered.value_origin.replaceAll("_", " ")}` : ""}
          {hovered.unknown_reason ? ` · ${hovered.unknown_reason}` : ""}
        </div>
      )}
    </div>
  );
}

const PROVENANCE_ORDER = [
  "accredited_laboratory", "internal_measurement", "supplier_declared", "peer_reviewed",
  "physics_simulation", "computed_database", "model_prediction", "handbook_typical",
  "engineering_estimate", "declared", "unknown", "none",
] as const;

const PROVENANCE_META: Record<string, { label: string; color: string }> = {
  accredited_laboratory: { label: "Accredited laboratory", color: "#1e5b48" },
  internal_measurement: { label: "Internal measurement", color: "#2f7d5c" },
  supplier_declared: { label: "Supplier datasheet", color: "#507d44" },
  peer_reviewed: { label: "Published literature", color: "#6e7041" },
  physics_simulation: { label: "Physics simulation", color: "#5b3f86" },
  computed_database: { label: "Computed database", color: "#4d5687" },
  model_prediction: { label: "Model prediction", color: "#1d5f7a" },
  handbook_typical: { label: "Reference handbook", color: "#9a7534" },
  engineering_estimate: { label: "Engineering estimate", color: "#9b5b2d" },
  declared: { label: "Declared / uncategorised", color: "#756a60" },
  unknown: { label: "Unknown provenance", color: "#8a8f96" },
  none: { label: "No value", color: "#c9b27a" },
};

/**
 * What each candidate's answers are actually made of.
 *
 * Phase 12.2 intentionally shows provenance rather than flattening every stored value into
 * "measured evidence". Supplier, handbook, computed-database and engineering-estimate values are
 * useful, but they are not interchangeable with a measurement and must not look interchangeable.
 */
export function EvidenceMix({ candidates }: { candidates: DecisionCandidate[] }) {
  if (!candidates.length) return null;

  const rowH = 30;
  const W = 780;
  const labelW = 240;
  const trackW = W - labelW - 60;
  const H = candidates.length * rowH + 78;
  const provenanceFor = (candidate: DecisionCandidate): Record<string, number> => {
    if (candidate.provenance_mix && Object.keys(candidate.provenance_mix).length) {
      return candidate.provenance_mix;
    }

    // Backward compatibility for cached/older Phase 12.1 decision-chart responses. The broad
    // `known_evidence` bucket is deliberately mapped to `declared`, never to a measurement class:
    // the old response does not contain enough provenance to make that stronger claim.
    const legacy: Record<string, number> = {};
    for (const [key, count] of Object.entries(candidate.origin_mix ?? {})) {
      const mapped = key === "model_prediction" ? "model_prediction"
        : key === "physics_simulation" ? "physics_simulation"
          : key === "none" ? "none"
            : "declared";
      legacy[mapped] = (legacy[mapped] ?? 0) + count;
    }
    return legacy;
  };

  const mixes = candidates.map(provenanceFor);
  const observedKeys = Array.from(new Set(mixes.flatMap((mix) => Object.keys(mix))));
  const legendKeys = PROVENANCE_ORDER.filter((key) => observedKeys.includes(key));

  return (
    <div className="chart-frame" data-testid="evidence-mix">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Evidence provenance mix per candidate">
        {candidates.map((candidate, i) => {
          const y = 12 + i * rowH;
          const mix = mixes[i];
          const total = Object.values(mix).reduce((a, b) => a + b, 0) || 1;
          let cursor = labelW;
          return (
            <g key={candidate.candidate_id}>
              <text x={0} y={y + 15} fontSize="12" fill="#18201d">
                {(candidate.display_name ?? "Candidate").slice(0, 28)}
              </text>
              {PROVENANCE_ORDER.filter((key) => mix[key]).map((key) => {
                const width = (mix[key] / total) * trackW;
                const meta = PROVENANCE_META[key] ?? PROVENANCE_META.unknown;
                const x = cursor;
                cursor += width;
                return (
                  <g key={key}>
                    <rect x={x} y={y + 3} width={Math.max(width, 1)} height={17}
                          fill={meta.color} fillOpacity={key === "none" ? 0.45 : 0.88} />
                    {width > 26 && (
                      <text x={x + width / 2} y={y + 16} fontSize="10.5" textAnchor="middle"
                            fill={key === "none" ? "#5f5130" : "white"} fontWeight={700}>
                        {mix[key]}
                      </text>
                    )}
                    <title>{`${meta.label}: ${mix[key]} of ${total} requirements`}</title>
                  </g>
                );
              })}
              <text x={W - 50} y={y + 16} fontSize="11" fill="#64706b">{total} req</text>
            </g>
          );
        })}
        <g transform={`translate(${labelW}, ${H - 44})`}>
          {legendKeys.slice(0, 6).map((key, i) => (
            <g key={key} transform={`translate(${(i % 3) * 175}, ${Math.floor(i / 3) * 18})`}>
              <rect width={10} height={10} y={-9} fill={PROVENANCE_META[key].color}
                    fillOpacity={key === "none" ? 0.45 : 0.88} />
              <text x={15} fontSize="10" fill="#64706b">{PROVENANCE_META[key].label.slice(0, 22)}</text>
            </g>
          ))}
        </g>
      </svg>
      <div className="muted">
        Provenance remains explicit: a supplier value, handbook figure, computed database result,
        model prediction and direct measurement are different evidence classes even when they support
        the same PASS/FAIL result.
      </div>
    </div>
  );
}
