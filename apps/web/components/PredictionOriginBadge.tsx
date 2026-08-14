export function PredictionOriginBadge({origin,status}:{origin?:string;status?:string}) {
  if (origin === "model_prediction") return <span className="badge">MODEL PREDICTION{status?` · ${status}`:""}</span>;
  if (origin === "known_evidence") return <span className="badge pass">KNOWN EVIDENCE</span>;
  return <span className="badge">UNKNOWN</span>;
}
