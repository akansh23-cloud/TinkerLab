const LABELS: Record<string,string> = {
  ready: "READY",
  not_applicable: "NOT APPLICABLE",
  incomplete_representation: "INCOMPLETE REPRESENTATION",
  provider_unavailable: "PROVIDER UNAVAILABLE",
  missing_registered_artifact: "MISSING REGISTERED ARTIFACT",
  unsupported_property: "UNSUPPORTED PROPERTY",
  unsupported_conditions: "UNSUPPORTED CONDITIONS",
};
export function RouteStatusBadge({status}:{status:string}){
  return <span className="badge" data-status={status}>{LABELS[status]??status.toUpperCase()}</span>;
}
