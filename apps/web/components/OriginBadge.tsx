import {OriginClass} from "@/lib/api";

// Scientific origins are rendered distinctly and never blended. A prediction that agrees with a
// simulation is still not a measurement, and the interface must not let them look alike.
const LABELS: Record<string,string> = {
  observed: "OBSERVED",
  literature: "LITERATURE",
  predicted: "PREDICTED",
  simulated: "SIMULATED",
  experimental: "EXPERIMENTAL",
  industrial: "INDUSTRIAL",
  unknown: "UNKNOWN ORIGIN",
};

export function OriginBadge({origin}:{origin:OriginClass|string}){
  return <span className="badge" data-origin={origin} data-testid={`origin-${origin}`}>
    {LABELS[origin]??String(origin).toUpperCase()}
  </span>;
}
