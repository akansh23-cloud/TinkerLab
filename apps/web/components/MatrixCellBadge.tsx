// A matrix cell must say what kind of answer it is before it says anything else. UNKNOWN,
// INCONCLUSIVE, NOT_COMPARABLE and CONFLICTING are first-class outcomes here, never blanks and
// never quietly rendered as a failure — a reader who skims must not mistake "we have not measured
// this" for "this candidate failed".
const LABELS: Record<string,string> = {
  pass: "PASS",
  fail: "FAIL",
  partial: "PARTIAL",
  unknown: "UNKNOWN — NO EVIDENCE",
  inconclusive: "INCONCLUSIVE",
  conflicting: "CONFLICTING EVIDENCE",
  not_comparable: "NOT COMPARABLE",
  not_applicable: "NOT APPLICABLE",
};

export function MatrixCellBadge({status}:{status:string}){
  return <span className="badge" data-matrix-status={status} data-testid={`matrix-${status}`}>
    {LABELS[status] ?? String(status).toUpperCase()}
  </span>;
}
