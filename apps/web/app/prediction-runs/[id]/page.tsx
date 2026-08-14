"use client";
import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, PredictionModelVersion, PredictionResultPage, PredictionRun } from "@/lib/api";
import { DemoModelWarning } from "@/components/DemoModelWarning";
import { PredictionInterval } from "@/components/PredictionInterval";

export default function PredictionRunPage({params}:{params:Promise<{id:string}>}) {
  const {id}=use(params); const run=useQuery({queryKey:["prediction-run",id],queryFn:()=>api<PredictionRun>(`/prediction-runs/${id}`)});
  const version=useQuery({queryKey:["prediction-version",run.data?.model_version_id],queryFn:()=>api<PredictionModelVersion>(`/prediction-model-versions/${run.data!.model_version_id}`),enabled:!!run.data});
  const results=useQuery({queryKey:["prediction-results",id],queryFn:()=>api<PredictionResultPage>(`/prediction-runs/${id}/results?offset=0&limit=200`)});
  if(run.isLoading) return <div className="empty">Loading prediction run…</div>;
  if(run.error||!run.data) return <div className="empty">Prediction run unavailable: {(run.error as Error)?.message}</div>;
  const r=run.data;
  return <div className="grid"><div className="topline"><div><div className="eyebrow">Prediction run</div><h1>{r.property_key}</h1><div className="muted">{r.status} · {r.requested_target_count} target(s)</div></div><Link className="btn btn-secondary" href={`/projects/${r.project_id}/prediction-lab`}>Prediction Lab</Link></div>
    <DemoModelWarning text={String(version.data?.immutable_metadata?.demo_warning??r.metadata?.demo_warning??"")}/>
    <div className="grid grid-2"><div className="card card-pad"><h2>Execution summary</h2><p>Predicted {r.predicted_count} · inapplicable {r.inapplicable_count} · failed {r.failed_count}</p><span className="kicker">Result checksum</span><p><code>{r.result_checksum??"—"}</code></p></div><div className="card card-pad"><h2>Model provenance</h2><p>Version {version.data?.version??"…"} · {version.data?.predictor_key??"…"}</p><p className="muted">artifact <code>{version.data?.artifact_checksum??"…"}</code></p><p className="muted">features <code>{version.data?.feature_schema_checksum??"…"}</code></p><p className="muted">conditions <code>{r.target_condition_checksum}</code></p></div></div>
    <div className="card"><div className="card-pad"><h2>Results</h2></div><div className="table-wrap"><table><thead><tr><th>Target</th><th>Prediction</th><th>Applicability</th><th>Status</th><th>Checksum</th></tr></thead><tbody>{results.data?.items.map(p=><tr key={p.id}><td><code>{String(p.target?.candidate_id??p.target?.hypothesis_id??p.target?.material_id??"").slice(0,12)}…</code></td><td><PredictionInterval point={p.numeric_point_estimate} lower={p.uncertainty_lower} upper={p.uncertainty_upper} unit={p.output_unit}/></td><td>{p.applicability_status}</td><td>{p.status}</td><td><Link href={`/predictions/${p.id}`}><code>{p.deterministic_result_checksum.slice(0,16)}…</code></Link></td></tr>)}</tbody></table></div></div>
  </div>;
}
