import type { GenerationRun } from "@/lib/api";
export function GenerationRunSummary({run}:{run:GenerationRun}) {
  return <div className="card card-pad" data-testid="generation-run-summary">
    <div className="topline" style={{marginBottom:12}}><div><div className="eyebrow">Generation run</div><h2 style={{margin:0}}>{run.strategy_key} <span className="muted">v{run.strategy_version}</span></h2></div><span className="badge">{run.status}</span></div>
    <div className="grid grid-2">
      <div><span className="kicker">Results</span><p>{run.generated_count} generated · {run.accepted_count} accepted · {run.rejected_count} rejected · {run.duplicate_count} duplicate</p></div>
      <div><span className="kicker">Seed / budget</span><p>{run.random_seed} / {run.requested_candidate_budget}</p></div>
      <div><span className="kicker">Specification</span><code>{run.replacement_specification_checksum.slice(0,16)}…</code></div>
      <div><span className="kicker">Search space</span><code>v{run.search_space_version} · {run.search_space_checksum.slice(0,16)}…</code></div>
      <div><span className="kicker">Configuration</span><code>{run.configuration_checksum.slice(0,16)}…</code></div>
      <div><span className="kicker">Result checksum</span><code>{run.result_checksum ? `${run.result_checksum.slice(0,16)}…` : "—"}</code></div>
    </div>
  </div>;
}
