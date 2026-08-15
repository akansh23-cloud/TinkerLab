"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {api, Constraint, Objective, ProjectDetail, ProjectSummary} from "@/lib/api";

function targetLabel(r: Constraint){
  if(r.target_boolean!==undefined&&r.target_boolean!==null) return `${r.comparator} ${String(r.target_boolean)}`;
  if(r.target_value_upper!==undefined&&r.target_value_upper!==null) return `${r.target_value ?? "—"}–${r.target_value_upper} ${r.target_unit??""}`.trim();
  return `${r.comparator} ${r.target_value ?? "—"} ${r.target_unit??""}`.trim();
}
function objectiveDirection(o: Objective){
  if(o.direction==="maximize") return "Maximize";
  if(o.direction==="minimize") return "Minimize";
  return o.direction.replaceAll("_"," ");
}

export default function RequirementsWorkspace(){
  const projects=useQuery({queryKey:["requirements-projects"],queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  const [selected,setSelected]=useState("");
  useEffect(()=>{if(!selected&&projects.data?.[0]?.id)setSelected(projects.data[0].id)},[projects.data,selected]);
  const project=useQuery({queryKey:["requirements-project",selected],enabled:!!selected,queryFn:()=>api<ProjectDetail>(`/replacement-projects/${selected}`)});
  const hard=project.data?.constraints.filter(r=>r.hard_or_soft==="hard")??[];
  const soft=project.data?.constraints.filter(r=>r.hard_or_soft!=="hard")??[];
  const objectives=project.data?.objectives??[];
  const severity=useMemo(()=>hard.reduce((n,r)=>n+r.severity,0),[hard]);

  return <div className="workspace-page requirements-workspace">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Requirements Engineering</span><h1>Define what a replacement must preserve.</h1><p>Separate blocking gates from optimization objectives so a strong score can never hide a critical failure.</p></div>
      <div className="hero-actions"><Link className="btn btn-secondary" href="/reasoning">Functional reasoning</Link><Link className="btn" href="/studies/new">+ New requirement set</Link></div>
    </div>

    <section className="command-kpis">
      <article><span className="metric-icon blue">◎</span><div><small>Blocking requirements</small><strong>{hard.length}</strong><em>Must be satisfied</em></div></article>
      <article><span className="metric-icon violet">◇</span><div><small>Soft requirements</small><strong>{soft.length}</strong><em>Tradeable preferences</em></div></article>
      <article><span className="metric-icon cyan">↗</span><div><small>Objectives</small><strong>{objectives.length}</strong><em>Ranking dimensions</em></div></article>
      <article><span className="metric-icon amber">!</span><div><small>Gate severity</small><strong>{severity||0}</strong><em>Declared criticality</em></div></article>
    </section>

    <section className="workspace-split requirements-split">
      <aside className="command-panel mission-list-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Replacement missions</span><h2>Select programme</h2></div><span className="count-chip">{projects.data?.length??0}</span></div>
        <div className="mission-selector-list">
          {(projects.data??[]).map(p=><button key={p.id} onClick={()=>setSelected(p.id)} className={selected===p.id?"active":""}><span className="mission-node">{p.baseline_material.display_name.slice(0,2).toUpperCase()}</span><span><strong>{p.name}</strong><small>{p.constraint_count} requirements · {p.candidate_count} candidates</small></span><i/></button>)}
          {projects.isLoading&&<div className="panel-empty">Loading missions…</div>}
          {!projects.isLoading&&projects.data?.length===0&&<div className="panel-empty">No missions yet. Create one to formalize replacement requirements.</div>}
        </div>
      </aside>

      <div className="command-panel requirements-canvas">
        <div className="panel-title-row"><div><span className="panel-kicker">Requirement architecture</span><h2>{project.data?.name??"Select a mission"}</h2><p>{project.data?.baseline_material?<>Baseline: <b>{project.data.baseline_material.display_name}</b> · {project.data.replacement_reasons.join(" · ")||"replacement study"}</>:"Choose a mission from the left."}</p></div>{project.data&&<Link href={`/projects/${project.data.id}`}>Open mission →</Link>}</div>
        {project.data&&<>
          <div className="requirement-legend"><span><i className="gate-dot hard"/> Blocking gate</span><span><i className="gate-dot soft"/> Soft requirement</span><span><i className="gate-dot objective"/> Optimization objective</span></div>
          <div className="requirement-stack">
            {project.data.constraints.map((r,index)=><article key={r.id} className={`requirement-card ${r.hard_or_soft==="hard"?"hard":"soft"}`}>
              <span className="requirement-index">R{String(index+1).padStart(2,"0")}</span>
              <div className="requirement-main"><div className="requirement-name"><strong>{r.property_key.replaceAll("_"," ")}</strong><span className={`badge ${r.hard_or_soft==="hard"?"fail":"unknown"}`}>{r.hard_or_soft==="hard"?"BLOCKING":"SOFT"}</span></div><p>Candidate evidence is evaluated independently against this declared threshold.</p></div>
              <div className="threshold-box"><small>Target</small><strong>{targetLabel(r)}</strong></div>
              <div className="weight-box"><small>Weight</small><b>{r.weight}</b><span>Severity {r.severity}</span></div>
            </article>)}
            {project.data.constraints.length===0&&<div className="panel-empty">This mission has no formal requirements yet.</div>}
          </div>
          {objectives.length>0&&<div className="objective-zone"><div className="panel-title-row minor"><div><span className="panel-kicker">Optimization</span><h3>Objectives after gates</h3></div></div><div className="objective-grid">{objectives.map(o=><article key={o.id}><span className="objective-symbol">↗</span><div><strong>{o.property_key.replaceAll("_"," ")}</strong><small>{objectiveDirection(o)} · priority {o.priority}</small></div><div className="objective-weight"><i style={{width:`${Math.min(100,Math.max(8,o.weight*100))}%`}}/><span>{Math.round(o.weight*100)}%</span></div></article>)}</div></div>}
        </>}
      </div>
    </section>

    <section className="command-panel requirement-principle">
      <div><span className="principle-icon">✓</span><div><span className="panel-kicker">Decision discipline</span><h2>A blocking failure cannot be averaged away.</h2><p>TinkerLab evaluates every gate independently. Missing evidence remains UNKNOWN; definitive violation becomes FAIL; only admissible supporting evidence can produce PASS.</p></div></div>
      <Link className="btn btn-secondary" href="/decisions">See decision outcomes</Link>
    </section>
  </div>;
}
