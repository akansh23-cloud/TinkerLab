export function HypothesisWarning({compact=false}:{compact?:boolean}) {
  return <div className="notice" role="note" data-testid="hypothesis-warning">
    <strong>Hypothesis — not a validated or experimentally confirmed material.</strong>
    {!compact && <div className="muted" style={{marginTop:6}}>Composition/process structure and lineage are proposals. Phase-4 model predictions, when present, are separate estimates with applicability and uncertainty; they are not measurements or physics validation.</div>}
  </div>;
}
