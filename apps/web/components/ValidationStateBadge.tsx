// "Validated" is never shown for simulation-only support. Each state says exactly what evidence
// stands behind it, so a reader cannot mistake computation for measurement.
const LABELS: Record<string,string> = {
  computational_only: "COMPUTATIONAL ONLY",
  simulation_supported: "SIMULATION SUPPORTED — NOT VALIDATED",
  experiment_recommended: "EXPERIMENT RECOMMENDED",
  experiment_pending: "EXPERIMENT PENDING",
  experiment_in_progress: "EXPERIMENT IN PROGRESS",
  partially_validated: "PARTIALLY VALIDATED",
  experimentally_supported: "EXPERIMENTALLY SUPPORTED",
  experimentally_contradicted: "EXPERIMENTALLY CONTRADICTED",
  conflicting_experiments: "CONFLICTING EXPERIMENTS",
  contradicted: "CONTRADICTED BY MEASUREMENT",
  inconclusive: "INCONCLUSIVE",
};

export function ValidationStateBadge({state}:{state:string}){
  return <span className="badge" data-state={state} data-testid={`validation-${state}`}>
    {LABELS[state]??String(state).toUpperCase()}
  </span>;
}
