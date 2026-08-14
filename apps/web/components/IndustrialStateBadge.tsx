import {IndustrialState} from "@/lib/api";

// UNKNOWN and INSUFFICIENT_EVIDENCE are rendered as loudly as PASS and FAIL. An absent answer is a
// real answer here, and must never look like a quiet success.
const LABELS: Record<string,string> = {
  pass: "PASS",
  fail: "FAIL",
  partial: "PARTIAL",
  unknown: "UNKNOWN",
  insufficient_evidence: "INSUFFICIENT EVIDENCE",
  conflicting_evidence: "CONFLICTING EVIDENCE",
};

export function IndustrialStateBadge({state}:{state:IndustrialState|string}){
  return <span className="badge" data-state={state} data-testid={`state-${state}`}>{LABELS[state]??String(state).toUpperCase()}</span>;
}
