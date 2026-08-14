// Operational completion and scientific convergence are different facts; this badge shows the latter.
const LABELS: Record<string,string> = {
  converged: "CONVERGED PHYSICS SIMULATION",
  unconverged: "UNCONVERGED — NO ACCEPTED VALUE",
  partial: "PARTIAL — NOT ACCEPTED",
  parser_failed: "PARSER FAILED — NO VALUE",
  not_applicable: "NOT APPLICABLE",
};
export function ConvergenceBadge({status}:{status?:string}){
  if(!status) return <span className="badge">NO RESULT</span>;
  return <span className="badge" data-status={status}>{LABELS[status]??status.toUpperCase()}</span>;
}
