import {IndustrialEvidence} from "@/lib/api";

// Renders the qualifiers that make an industrial number meaningful. If a figure is shown without
// them anywhere in this app, that is a bug: a bare number invites an invalid comparison.
export function EvidenceQualifiers({evidence}:{evidence:IndustrialEvidence}){
  const parts:string[] = [];
  if(evidence.currency||evidence.currency_year||evidence.cost_basis){
    parts.push(`${evidence.currency??"currency?"} ${evidence.currency_year??"year?"} · ${evidence.cost_basis??"basis?"}`);
  }
  if(evidence.geography) parts.push(`geography ${evidence.geography}`);
  if(evidence.jurisdiction) parts.push(`jurisdiction ${evidence.jurisdiction}`);
  parts.push(evidence.as_of_date?`as of ${evidence.as_of_date}`:"NO AS-OF DATE");
  return <div className="muted" data-testid="evidence-qualifiers">
    {parts.join(" · ")}
    {evidence.is_estimate&&<> · <strong>ESTIMATE</strong></>}
    <> · source {evidence.source_type}</>
  </div>;
}
