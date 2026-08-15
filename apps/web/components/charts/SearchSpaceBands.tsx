"use client";
import { formatValue } from "@/lib/charts";
import type { CandidateSearchSpace } from "@/lib/api";

/**
 * The search space, drawn as the thing it actually is: a set of composition bands around the
 * incumbent formulation.
 *
 * Before this, the space existed only as a table of min/max/step numbers and a checksum, and it was
 * genuinely hard to see whether a derived space was sensibly bounded or whether one component had
 * been left free to swing across a range that makes no formulation sense. One glance at the bands
 * answers that.
 *
 * Locked components are drawn as a point, not a zero-width band — they are fixed by a decision
 * (matrix, redacted amount, dopant), not by a band that happens to be narrow, and the two mean
 * different things to whoever reviews the space.
 */
export function SearchSpaceBands({ space }: { space: CandidateSearchSpace }) {
  const rules = [...space.component_rules].sort((a, b) => a.sequence - b.sequence);
  if (!rules.length) return <div className="empty">This search space has no component rules.</div>;

  const rowH = 34;
  const W = 780;
  const labelW = 220;
  const trackW = W - labelW - 110;
  const H = rules.length * rowH + 46;

  const amounts = rules.flatMap((r) => [
    r.min_amount ?? null,
    r.max_amount ?? null,
    typeof r.metadata?.baseline_amount === "number" ? (r.metadata.baseline_amount as number) : null,
  ]).filter((v): v is number => v !== null);
  const percentBasis = space.amount_basis.toLowerCase().includes("percent");
  const inferredMax = amounts.length ? Math.max(...amounts) : 1;
  const max = Math.max(space.total_target ?? (percentBasis ? 100 : inferredMax), inferredMax, 1);
  const axisUnit = rules.find((r) => r.amount_unit)?.amount_unit ?? (percentBasis ? "%" : space.amount_basis);
  const ticks = Array.from({ length: 5 }, (_, i) => (max * i) / 4);
  const scale = (v: number) => labelW + (Math.min(Math.max(v, 0), max) / max) * trackW;

  return (
    <div className="chart-frame" data-testid="search-space-bands">
      <div className="chart-title">
        Composition bands · version {space.version} · {space.amount_basis.replaceAll("_", " ")}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Composition variation bands per component">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={scale(t)} y1={14} x2={scale(t)} y2={H - 26} stroke="#dce3df" strokeDasharray="2 3" />
            <text x={scale(t)} y={H - 12} fontSize="10" textAnchor="middle" fill="#8a8f96">
              {formatValue(t)}{axisUnit ? ` ${axisUnit}` : ""}
            </text>
          </g>
        ))}

        {rules.map((rule, i) => {
          const y = 18 + i * rowH;
          const baseline = typeof rule.metadata?.baseline_amount === "number"
            ? (rule.metadata.baseline_amount as number) : null;
          const isBalance = space.balance_component_key === rule.component_key;

          return (
            <g key={rule.id}>
              <text x={0} y={y + 12} fontSize="12" fill="#18201d"
                    fontWeight={rule.mutable ? 650 : 400}>
                {rule.display_name.slice(0, 24)}
              </text>
              <text x={0} y={y + 24} fontSize="9.5" fill="#8a8f96">
                {rule.mutable ? "varies" : isBalance ? "balance — absorbs remainder" : "held fixed"}
                {rule.role ? ` · ${rule.role}` : ""}
              </text>

              {rule.mutable && rule.min_amount !== undefined && rule.max_amount !== undefined
                && rule.min_amount !== null && rule.max_amount !== null && (
                <>
                  <rect x={scale(rule.min_amount)} y={y + 3}
                        width={Math.max(scale(rule.max_amount) - scale(rule.min_amount), 2)} height={15}
                        rx={3} fill="#1e5b48" fillOpacity={0.2} stroke="#1e5b48" strokeOpacity={0.55} />
                  {/* step ticks, so an unusably coarse grid is visible rather than buried in a number */}
                  {rule.step_amount && (rule.max_amount - rule.min_amount) / rule.step_amount <= 40 &&
                    Array.from(
                      { length: Math.floor((rule.max_amount - rule.min_amount) / rule.step_amount) + 1 },
                      (_, k) => rule.min_amount! + k * rule.step_amount!,
                    ).map((v) => (
                      <line key={v} x1={scale(v)} y1={y + 5} x2={scale(v)} y2={y + 16}
                            stroke="#1e5b48" strokeOpacity={0.35} />
                    ))}
                  <text x={scale(rule.max_amount) + 8} y={y + 15} fontSize="10.5" fill="#1e5b48" fontWeight={650}>
                    {formatValue(rule.min_amount)}–{formatValue(rule.max_amount)}
                    {rule.step_amount ? ` step ${formatValue(rule.step_amount)}` : ""}
                  </text>
                </>
              )}

              {baseline !== null && (
                <>
                  <line x1={scale(baseline)} y1={y} x2={scale(baseline)} y2={y + 21}
                        stroke="#18201d" strokeWidth={2} />
                  <circle cx={scale(baseline)} cy={y + 10.5} r={3.5} fill="#18201d" />
                  <title>{`${rule.display_name}: incumbent at ${baseline}${rule.amount_unit ?? "%"}`}</title>
                </>
              )}

              {!rule.mutable && baseline === null && (
                <text x={labelW} y={y + 15} fontSize="10.5" fill="#8a8f96">
                  no numeric amount recorded on the incumbent
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="muted">
        The dark marker is the incumbent’s own amount; the band is what candidate generation may
        explore around it. Ticks are the discrete steps actually enumerated.
      </div>
    </div>
  );
}
