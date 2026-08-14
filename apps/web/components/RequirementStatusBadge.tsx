import {RequirementStatusValue} from "@/lib/api";

// Every non-verdict outcome gets its own visible label. UNKNOWN must never be mistaken for a pass,
// and STATE_MISMATCH must never be mistaken for "no data".
const LABELS: Record<string,string> = {
  pass: "PASS",
  fail: "FAIL",
  partial: "PARTIAL",
  unknown: "UNKNOWN",
  insufficient_evidence: "INSUFFICIENT EVIDENCE",
  conflicting_evidence: "CONFLICTING EVIDENCE",
  state_mismatch: "WRONG MATERIAL STATE",
};

export function RequirementStatusBadge({status}:{status:RequirementStatusValue|string}){
  return <span className="badge" data-status={status} data-testid={`req-${status}`}>
    {LABELS[status]??String(status).toUpperCase()}
  </span>;
}
