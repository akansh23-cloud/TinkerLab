"use client";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {api,ProjectSummary} from "@/lib/api";
export default function VirtualLabIndex(){
  const projects=useQuery({queryKey:["projects"],queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  return <><div className="page-title-row"><div><div className="eyebrow">Virtual Experiment Lab</div><h1>Choose a replacement mission</h1><p className="muted">Open an industrial test visualization linked to the selected mission evidence.</p></div><Link className="btn" href="/studies/new">New study</Link></div><div className="mission-grid">
    {(projects.data??[]).map((p,i)=><Link className="mission-select-card" href={`/projects/${p.id}/virtual-lab`} key={p.id}><span className={`mission-icon mission-icon-${i%3}`}>⌬</span><div><small>{p.status.toUpperCase()}</small><h2>{p.name}</h2><p>{p.description||"Evidence-linked replacement programme"}</p></div><div className="mission-select-meta"><span>{p.candidate_count} candidates</span><span>{p.constraint_count} requirements</span><b>Open lab →</b></div></Link>)}
    {projects.isLoading&&<div className="card card-pad">Loading replacement missions…</div>}{projects.error&&<div className="notice fail">Could not load projects: {(projects.error as Error).message}</div>}{projects.data?.length===0&&<div className="card card-pad"><h2>No replacement missions yet</h2><p className="muted">Create a study or load the flagship demo from Mission Control first.</p><Link className="btn" href="/">Go to Mission Control</Link></div>}
  </div></>;
}
