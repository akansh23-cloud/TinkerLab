"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {api, ProjectSummary, ReplacementProgramRecord, TechnicalDossierRecord, TimelineEventRecord} from "@/lib/api";

function shortHash(v:string){return v?`${v.slice(0,10)}…${v.slice(-6)}`:"—"}
function when(v:string){const d=new Date(v);return Number.isNaN(d.getTime())?v:d.toLocaleString(undefined,{month:"short",day:"numeric",year:"numeric",hour:"2-digit",minute:"2-digit"})}

export default function ReportsWorkspace(){
  const qc=useQueryClient();
  const projects=useQuery({queryKey:["reports-projects"],queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  const [projectId,setProjectId]=useState("");const [programChoice,setProgramChoice]=useState("");
  useEffect(()=>{if(!projectId&&projects.data?.[0]?.id)setProjectId(projects.data[0].id)},[projects.data,projectId]);
  const programs=useQuery({queryKey:["reports-programs",projectId],enabled:!!projectId,queryFn:()=>api<ReplacementProgramRecord[]>(`/replacement-programs?project_id=${encodeURIComponent(projectId)}`)});
  const programId=programChoice||programs.data?.[0]?.id||"";
  const dossiers=useQuery({queryKey:["reports-dossiers",programId],enabled:!!programId,queryFn:()=>api<TechnicalDossierRecord[]>(`/replacement-programs/${programId}/dossiers`)});
  const timeline=useQuery({queryKey:["reports-timeline",programId],enabled:!!programId,queryFn:()=>api<TimelineEventRecord[]>(`/replacement-programs/${programId}/timeline?limit=30`)});
  const generate=useMutation({mutationFn:()=>api<TechnicalDossierRecord>(`/replacement-programs/${programId}/dossier`,{method:"POST",body:"{}"}),onSuccess:()=>qc.invalidateQueries({queryKey:["reports-dossiers",programId]})});
  const latest=dossiers.data?.[0];

  return <div className="workspace-page reports-workspace">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Technical Reports</span><h1>Turn the decision into an auditable engineering dossier.</h1><p>Every generated report is versioned, checksummed, methodology-tagged, and built from stored evidence—not generated narrative.</p></div>
      <div className="hero-actions">{projectId&&<Link className="btn btn-secondary" href={`/projects/${projectId}/replacement`}>Decision Mission</Link>}<button className="btn" onClick={()=>generate.mutate()} disabled={!programId||generate.isPending}>{generate.isPending?"Generating…":"Generate technical dossier"}</button></div>
    </div>

    <div className="report-selector command-panel"><label><small>Mission</small><select value={projectId} onChange={e=>{setProjectId(e.target.value);setProgramChoice("")}}>{(projects.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label><small>Programme</small><select value={programId} onChange={e=>setProgramChoice(e.target.value)}>{(programs.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><div><small>Report policy</small><strong>Deterministic · versioned · evidence-linked</strong></div></div>

    <section className="command-kpis">
      <article><span className="metric-icon blue">▤</span><div><small>Dossier versions</small><strong>{dossiers.data?.length??0}</strong><em>Historical versions preserved</em></div></article>
      <article><span className="metric-icon cyan">#</span><div><small>Evidence references</small><strong>{latest?.evidence_ids.length??0}</strong><em>Latest dossier</em></div></article>
      <article><span className="metric-icon violet">§</span><div><small>Methodologies</small><strong>{latest?Object.keys(latest.methodology_versions).length:0}</strong><em>Explicit calculation versions</em></div></article>
      <article><span className="metric-icon green">✓</span><div><small>Generative narrative</small><strong>OFF</strong><em>Structured scientific output</em></div></article>
    </section>

    <section className="reports-grid">
      <div className="command-panel dossier-preview">
        <div className="panel-title-row"><div><span className="panel-kicker">Latest technical dossier</span><h2>{latest?.title??"No dossier generated yet"}</h2><p>{latest?`Version ${latest.version} · generated ${when(latest.generated_at)}`:"Generate the first version after a programme has evidence and a decision state."}</p></div>{latest&&<span className="version-chip">v{latest.version}</span>}</div>
        {latest?<>
          <div className="dossier-cover"><div className="dossier-logo"><span className="brand-mark tiny"><span/></span><b>TinkerLab</b></div><div><span>TECHNICAL REPLACEMENT DOSSIER</span><h3>{latest.title}</h3><p>Evidence-backed material replacement record</p></div><div className="dossier-meta"><span>Programme</span><strong>{programs.data?.find(p=>p.id===programId)?.name??programId}</strong><span>Generated</span><strong>{when(latest.generated_at)}</strong><span>Checksum</span><code>{shortHash(latest.dossier_checksum)}</code></div></div>
          <div className="dossier-sections">{latest.sections.slice(0,12).map(s=><article key={s.number}><span>{String(s.number).padStart(2,"0")}</span><strong>{s.title}</strong><small>{Object.keys(s.content).length} structured field{Object.keys(s.content).length===1?"":"s"}</small></article>)}</div>
          <div className="report-integrity"><span>✓</span><div><strong>Integrity boundary</strong><p>Report values are read from stored platform state. This dossier declares <b>{latest.llm_narrative_used?"AI narrative used":"no generative narrative"}</b>.</p></div></div>
        </>:<div className="panel-empty large"><span className="empty-document">▤</span><h3>No dossier exists for this programme.</h3><p>Generate one to snapshot the decision, evidence references, methodology versions, and technical rationale.</p><button className="btn" disabled={!programId||generate.isPending} onClick={()=>generate.mutate()}>Generate first dossier</button></div>}
      </div>

      <aside className="command-panel report-history-panel"><div className="panel-title-row"><div><span className="panel-kicker">Report history</span><h2>Immutable versions</h2></div></div><div className="report-history">{(dossiers.data??[]).map((d,i)=><article key={d.id} className={i===0?"active":""}><span className="report-version">v{d.version}</span><div><strong>{d.title}</strong><small>{when(d.generated_at)}</small><code>{shortHash(d.dossier_checksum)}</code></div><b>{d.evidence_ids.length} refs</b></article>)}{!dossiers.isLoading&&(dossiers.data?.length??0)===0&&<div className="panel-empty">Versions appear here after generation.</div>}</div></aside>
    </section>

    <section className="workspace-split reports-bottom">
      <div className="command-panel"><div className="panel-title-row"><div><span className="panel-kicker">Methodology manifest</span><h2>What produced this result?</h2></div></div><div className="method-list">{Object.entries(latest?.methodology_versions??{}).map(([k,v])=><div key={k}><span>{k.replaceAll("_"," ")}</span><code>{v}</code></div>)}{!latest&&<div className="panel-empty">Method versions are captured when a dossier is generated.</div>}</div></div>
      <div className="command-panel"><div className="panel-title-row"><div><span className="panel-kicker">Audit timeline</span><h2>Recent programme events</h2></div></div><div className="audit-list">{(timeline.data??[]).slice(0,8).map(e=><article key={e.id}><span className="audit-node"/><div><strong>{e.event_kind.replaceAll("_"," ")}</strong><p>{e.summary}</p></div><time>{when(e.occurred_at)}</time></article>)}{!timeline.isLoading&&(timeline.data?.length??0)===0&&<div className="panel-empty">No programme events recorded.</div>}</div></div>
    </section>
  </div>;
}
