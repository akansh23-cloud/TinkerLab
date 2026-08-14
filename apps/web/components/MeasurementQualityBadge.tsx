// A measurement that is not admissible says why. Silence would let an untraceable number look
// like evidence.
const LABELS: Record<string,string> = {
  accepted: "ACCEPTED",
  provisional: "PROVISIONAL",
  rejected: "REJECTED",
  incomplete_provenance: "INCOMPLETE PROVENANCE — NOT EVIDENCE",
  invalidated_source: "INVALIDATED SOURCE — HISTORY ONLY",
};

export function MeasurementQualityBadge({quality}:{quality:string}){
  return <span className="badge" data-quality={quality} data-testid={`quality-${quality}`}>
    {LABELS[quality]??String(quality).toUpperCase()}
  </span>;
}
