"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, ProjectSummary } from "@/lib/api";

export default function Dashboard() {
  const {data, error, isLoading} = useQuery({queryKey:["projects"], queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  const active = data?.filter(p=>p.status === "active").length ?? 0;
  const constraints = data?.reduce((n,p)=>n+p.constraint_count,0) ?? 0;
  const candidates = data?.reduce((n,p)=>n+p.candidate_count,0) ?? 0;
  return <>
    <div className="topline"><div><div className="eyebrow">Scientific workspace</div><h1>Replacement studies</h1><div className="muted">Define what must change, preserve evidence, and compare alternatives without fabricated results.</div></div><Link className="btn" href="/projects/new">New study</Link></div>
    <div className="notice" style={{marginBottom:18}}>Seeded values are explicitly demonstration data. TinkerLab Phase 2 preserves source records, conditions, conflicting observations, and selection rationale. It still does not generate materials, predict properties, or run physics simulations.</div>
    <div className="grid grid-3" style={{marginBottom:18}}>
      <div className="card stat"><span className="kicker">Active studies</span><strong>{active}</strong></div>
      <div className="card stat"><span className="kicker">Formal constraints</span><strong>{constraints}</strong></div>
      <div className="card stat"><span className="kicker">Attached candidates</span><strong>{candidates}</strong></div>
    </div>
    <div className="card">
      <div className="card-pad" style={{borderBottom:"1px solid var(--line)"}}><h2>Projects</h2></div>
      {isLoading && <div className="empty">Loading scientific workspace…</div>}
      {error && <div className="empty">API unavailable: {(error as Error).message}</div>}
      {data && <div className="table-wrap"><table><thead><tr><th>Study</th><th>Baseline</th><th>Reasons</th><th>Constraints</th><th>Candidates</th><th>Status</th></tr></thead><tbody>{data.map(p=><tr key={p.id}>
        <td><Link href={`/projects/${p.id}`}><strong>{p.name}</strong></Link><div className="muted" style={{fontSize:12,marginTop:3}}>{p.description}</div></td>
        <td><Link href={`/materials/${p.baseline_material.id}`}>{p.baseline_material.display_name}</Link></td>
        <td>{p.replacement_reasons.join(", ")}</td><td>{p.constraint_count}</td><td>{p.candidate_count}</td><td><span className="badge">{p.status}</span></td>
      </tr>)}</tbody></table></div>}
    </div>
  </>;
}
