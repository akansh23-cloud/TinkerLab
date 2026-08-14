// A gap is missing evidence, never a verdict. The wording deliberately avoids "failed" so that a
// blocking gap is read as outstanding work rather than as a rejection.
const LABELS: Record<string,string> = {
  blocking_gap: "BLOCKING GAP",
  high_value_gap: "HIGH-VALUE GAP",
  normal_gap: "GAP",
  optional_gap: "OPTIONAL GAP",
};

export function EvidenceGapBadge({gapClass}:{gapClass:string}){
  return <span className="badge" data-gap-class={gapClass} data-testid={`gap-${gapClass}`}>
    {LABELS[gapClass] ?? String(gapClass).toUpperCase()}
  </span>;
}
