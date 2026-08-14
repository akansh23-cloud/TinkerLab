"use client";
import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, CandidatePage, GenerationRun } from "@/lib/api";
import { GenerationRunSummary } from "@/components/GenerationRunSummary";
import { HypothesisWarning } from "@/components/HypothesisWarning";

export default function GenerationRunPage({params}:{params:Promise<{id:string}>}) {
  const {id}=use(params);
  const run=useQuery({queryKey:["generation-run",id],queryFn:()=>api<GenerationRun>(`/generation-runs/${id}`)});
  const candidates=useQuery({queryKey:["generation-run-candidates",id],queryFn:()=>api<CandidatePage>(`/generation-runs/${id}/candidates?offset=0&limit=200`)});
  if(run.isLoading) return <div className="empty">Loading generation run…</div>;
  if(run.error||!run.data) return <div className="empty">Generation run unavailable: {(run.error as Error)?.message}</div>;
  return <div className="grid"><div className="topline"><div><div className="eyebrow">Auditable generation history</div><h1>Generation run</h1></div><Link className="btn btn-secondary" href={`/projects/${run.data.project_id}/candidate-lab`}>Candidate Lab</Link></div><GenerationRunSummary run={run.data}/><HypothesisWarning compact/><div className="card"><div className="card-pad"><h2>Ordered run results</h2><p className="muted">The result checksum is derived from the deterministic ordered fingerprint sequence. Duplicate outcomes remain counted rather than silently disappearing.</p></div><div className="table-wrap"><table><thead><tr><th>Candidate</th><th>Kind</th><th>Status</th><th>Fingerprint</th><th>Evidence posture</th></tr></thead><tbody>{candidates.data?.items.map(c=><tr key={c.id}><td>{c.candidate_kind==="hypothesis"&&c.hypothesis_id?<Link href={`/candidate-hypotheses/${c.hypothesis_id}`}>{c.display_name}</Link>:c.material_id?<Link href={`/materials/${c.material_id}`}>{c.display_name}</Link>:c.display_name}</td><td>{c.candidate_kind}</td><td>{c.status}</td><td><code>{c.deterministic_fingerprint?.slice(0,18)??"—"}…</code></td><td>{c.evidence_posture}</td></tr>)}</tbody></table></div></div></div>;
}
