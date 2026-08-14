// Priority is a transparent decision-value score, not a probability. The badge shows the band and
// the exact number, and the tooltip carries the formula so the figure can always be reproduced.
export function ActionPriorityBadge({priority,factors}:{priority:number;factors?:Record<string,unknown>}){
  const band = priority >= 0.6 ? "high" : priority >= 0.3 ? "medium" : "low";
  const formula = typeof factors?.formula === "string" ? factors.formula : undefined;
  return <span className="badge" data-priority-band={band} data-testid={`priority-${band}`}
    title={formula ? `${formula} — not a probability` : "Transparent decision-value score — not a probability"}>
    PRIORITY {priority.toFixed(3)}
  </span>;
}
