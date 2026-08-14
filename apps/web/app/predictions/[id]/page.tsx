"use client";
import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, PredictionDetail } from "@/lib/api";
import { DemoModelWarning } from "@/components/DemoModelWarning";
import { PredictionInterval } from "@/components/PredictionInterval";
import { PredictionOriginBadge } from "@/components/PredictionOriginBadge";

export default function PredictionDetailPage({params}:{params:Promise<{id:string}>}) {
  const {id}=use(params); const q=useQuery({queryKey:["prediction",id],queryFn:()=>api<PredictionDetail>(`/predictions/${id}`)});
  if(q.isLoading) return <div className="empty">Loading prediction provenance…</div>;
  if(q.error||!q.data) return <div className="empty">Prediction unavailable: {(q.error as Error)?.message}</div>;
  const d=q.data,p=d.prediction; const mv=d.model_version as Record<string,unknown>; const fs=d.feature_snapshot as Record<string,unknown>;
  return <div className="grid"><div className="topline"><div><div className="eyebrow">Prediction provenance</div><h1>Property prediction</h1><PredictionOriginBadge origin="model_prediction"/></div><Link className="btn btn-secondary" href={`/prediction-runs/${p.prediction_run_id}`}>Prediction run</Link></div><DemoModelWarning text={d.demo_warning}/>
    <div className="grid grid-2"><div className="card card-pad"><h2>Result</h2><PredictionInterval point={p.numeric_point_estimate} lower={p.uncertainty_lower} upper={p.uncertainty_upper} unit={p.output_unit}/><p><span className="kicker">Applicability</span><br/><span className="badge">{p.applicability_status}</span></p><p className="muted">{p.uncertainty_method} · calibrated coverage {p.calibrated_coverage_level??"—"}</p>{p.applicability_rationale.map((r,i)=><div className="muted" key={i}>{String(r.code??"APPLICABILITY")}: {String(r.message??"")}</div>)}</div><div className="card card-pad"><h2>Reproducibility</h2><span className="kicker">Result checksum</span><p><code>{p.deterministic_result_checksum}</code></p><span className="kicker">Feature checksum</span><p><code>{String(fs.feature_checksum??"—")}</code></p><span className="kicker">Model artifact checksum</span><p><code>{String(mv.artifact_checksum??"—")}</code></p></div></div>
    <div className="card card-pad"><h2>Model validation metadata</h2><p className="muted">These metrics describe the registered model artifact; they are not experimental validation of this candidate.</p><pre className="json">{JSON.stringify({validation_metrics:mv.validation_metrics,calibration_metrics:mv.calibration_metrics,feature_schema_version:mv.feature_schema_version,applicability_policy_version:mv.applicability_policy_version},null,2)}</pre></div>
    <div className="card card-pad"><h2>Input snapshot summary</h2><p className="muted">This scoped detail view exposes the normalized feature snapshot used for inference. Normal list APIs do not return private feature vectors.</p><pre className="json">{JSON.stringify(fs,null,2)}</pre></div>
    {p.warnings.length>0&&<div className="notice">{p.warnings.map(w=><div key={w}>{w}</div>)}</div>}
  </div>;
}
