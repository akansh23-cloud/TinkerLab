// Program state is resolved from evidence, not chosen by the user. PAUSED and ARCHIVED are the only
// two an operator can set, and they are labelled so it is clear they express intent, not a finding.
const LABELS: Record<string,string> = {
  draft: "DRAFT",
  requirements_defined: "REQUIREMENTS DEFINED",
  candidates_generated: "CANDIDATES GENERATED",
  screening: "SCREENING",
  validating: "VALIDATING",
  experimenting: "EXPERIMENTING",
  converging: "CONVERGING",
  decision_ready: "DECISION READY",
  recommended: "RECOMMENDED",
  no_suitable_candidate: "NO SUITABLE CANDIDATE",
  paused: "PAUSED (SET BY OPERATOR)",
  archived: "ARCHIVED (SET BY OPERATOR)",
};

export function ProgramStateBadge({state}:{state:string}){
  return <span className="badge" data-program-state={state} data-testid={`program-${state}`}>
    {LABELS[state] ?? String(state).toUpperCase()}
  </span>;
}
