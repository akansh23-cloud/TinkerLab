"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {
  api, DecisionMatrix, PortfolioBoard, ProgramGaps, ProjectSummary, ReplacementProgramRecord,
  ReplacementRecommendationRecord, ScientificActionRecord,
} from "@/lib/api";

function decisionFor(id:string,row:{eligibility:string;gates_satisfied:boolean},rec?:ReplacementRecommendationRecord){
  if(rec?.recommended_candidate_ids.includes(id)) return "ADVANCE";
  if(rec?.rejected_candidate_ids.includes(id)) return "REJECT";
  if(rec?.held_candidate_ids.includes(id)) return "HOLD / TEST";
  if(row.eligibility==="blocked") return "REJECT";
  return row.gates_satisfied?"ADVANCE":"HOLD / TEST";
}
function cls(d:string){return d.startsWith("ADVANCE")?"advance":d.startsWith("REJECT")?"reject":"hold"}
function pct(v:number){return `${Math.max(0,Math.min(100,Math.round(v*100)))}%`}

export default function DecisionsWorkspace(){
  const projects=useQuery({queryKey:["decisions-projects"],queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  const [projectId,setProjectId]=useState("");
  const [programChoice,setProgramChoice]=useState("");
  useEffect(()=>{if(!projectId&&projects.data?.[0]?.id)setProjectId(projects.data[0].id)},[projects.data,projectId]);
  const programs=useQuery({queryKey:["decisions-programs",projectId],enabled:!!projectId,queryFn:()=>api<ReplacementProgramRecord[]>(`/replacement-programs?project_id=${encodeURIComponent(projectId)}`)});
  const programId=programChoice||programs.data?.[0]?.id||"";
  useEffect(()=>{if(programChoice&&programs.data&&!programs.data.some(p=>p.id===programChoice))setProgramChoice("")},[programs.data,programChoice]);
  const board=useQuery({queryKey:["decisions-board",programId],enabled:!!programId,queryFn:()=>api<PortfolioBoard>(`/replacement-programs/${programId}/portfolio`)});
  const matrix=useQuery({queryKey:["decisions-matrix",programId],enabled:!!programId,queryFn:()=>api<DecisionMatrix>(`/replacement-programs/${programId}/decision-matrix`)});
  const gaps=useQuery({queryKey:["decisions-gaps",programId],enabled:!!programId,queryFn:()=>api<ProgramGaps>(`/replacement-programs/${programId}/evidence-gaps`)});
  const actions=useQuery({queryKey:["decisions-actions",programId],enabled:!!programId,queryFn:()=>api<ScientificActionRecord[]>(`/replacement-programs/${programId}/actions?status=open`)});
  const recommendation=useQuery({queryKey:["decisions-rec",programId],enabled:!!programId,queryFn:()=>api<ReplacementRecommendationRecord>(`/replacement-programs/${programId}/recommendation?preview=true`)});
  const activeProject=projects.data?.find(p=>p.id===projectId);
  const candidates=board.data?.candidates??[];
  const decisions=useMemo(()=>candidates.map(c=>decisionFor(c.candidate_id,c,recommendation.data)),[candidates,recommendation.data]);
  const advance=decisions.filter(d=>d==="ADVANCE").length,reject=decisions.filter(d=>d==="REJECT").length,hold=decisions.filter(d=>d==="HOLD / TEST").length;

  return <div className="workspace-page decisions-workspace">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Replacement Decision Story</span><h1>Make the decision understandable in one screen.</h1><p>See which candidates advance, fail, or remain unresolved—and trace every outcome back to requirements and evidence.</p></div>
      <div className="hero-actions"><Link className="btn btn-secondary" href="/reasoning">Deep reasoning</Link>{projectId&&<Link className="btn" href={`/projects/${projectId}/replacement`}>Open Mission Control</Link>}</div>
    </div>

    <div className="decision-selector command-panel">
      <label><small>Replacement mission</small><select value={projectId} onChange={e=>{setProjectId(e.target.value);setProgramChoice("")}}>{(projects.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label><small>Decision programme</small><select value={programId} onChange={e=>setProgramChoice(e.target.value)}>{(programs.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <div className="selector-context"><span>INCUMBENT</span><strong>{activeProject?.baseline_material.display_name??"—"}</strong><small>{activeProject?.constraint_count??0} declared requirements</small></div>
    </div>

    <section className="decision-outcome-kpis">
      <article className="advance"><small>Advance</small><strong>{advance}</strong><span>Gates satisfied</span></article>
      <article className="reject"><small>Reject</small><strong>{reject}</strong><span>Blocking failure</span></article>
      <article className="hold"><small>Hold / Test</small><strong>{hold}</strong><span>Evidence unresolved</span></article>
      <article className="neutral"><small>Blocking gaps</small><strong>{gaps.data?.blocking_gap_count??0}</strong><span>Need resolution</span></article>
    </section>

    {!programs.isLoading&&programs.data?.length===0&&<section className="command-panel panel-empty large"><h2>No replacement decision programme exists for this mission yet.</h2><p>Create or open the mission workflow to bind candidates to a formal decision policy.</p><Link className="btn" href={projectId?`/projects/${projectId}`:"/studies/new"}>Open mission</Link></section>}

    {programId&&<>
      <section className="candidate-decision-grid">
        {candidates.slice(0,4).map((c,index)=>{
          const d=decisionFor(c.candidate_id,c,recommendation.data);const state=cls(d);
          const cells=(matrix.data?.rows??[]).map(r=>({r,cell:r.cells[c.candidate_id]})).filter(x=>x.cell);
          const pass=cells.filter(x=>x.cell.status==="pass").length;
          const fail=cells.filter(x=>x.cell.status==="fail").length;
          const unknown=cells.filter(x=>!["pass","fail"].includes(x.cell.status)).length;
          const risk=Math.min(100,c.blocking_failure_count*38+c.conflict_count*22+c.unknown_count*10);
          return <article className={`candidate-decision-card ${state}`} key={c.candidate_id}>
            <div className="candidate-card-top"><div><span>CANDIDATE {String.fromCharCode(65+index)}</span><h2>{c.display_name}</h2><p>{d==="ADVANCE"?"All currently evaluated blocking gates are satisfied.":d==="REJECT"?"Definitive evidence violates at least one blocking requirement.":"The candidate remains scientifically unresolved; more evidence is required."}</p></div><b>{d}</b></div>
            <div className="decision-ring-row">
              <div className="metric-ring" style={{"--value":`${Math.round(c.evidence_coverage*360)}deg`} as any}><span><strong>{pct(c.evidence_coverage)}</strong><small>Coverage</small></span></div>
              <div className="metric-ring confidence" style={{"--value":`${Math.round(Math.max(0,100-risk)*3.6)}deg`} as any}><span><strong>{Math.max(0,100-risk)}%</strong><small>Readiness</small></span></div>
              <div className="metric-ring risk" style={{"--value":`${Math.round(risk*3.6)}deg`} as any}><span><strong>{risk}%</strong><small>Risk</small></span></div>
            </div>
            <div className="requirement-mini-table"><div><span>Requirement state</span><span>Outcome</span></div>{cells.slice(0,5).map(({r,cell})=><div key={r.requirement_id}><span>{r.display_name}</span><b className={`cell-state ${cell.status}`}>{cell.status.toUpperCase()}</b></div>)}</div>
            <div className="candidate-card-foot"><span className={fail?"bad":unknown?"warn":"good"}>{fail?`${fail} blocking failure${fail===1?"":"s"}`:unknown?`${unknown} unresolved requirement${unknown===1?"":"s"}`:`${pass} evaluated requirements satisfied`}</span><Link href={`/projects/${projectId}/replacement`}>Explain →</Link></div>
          </article>
        })}
        {board.isLoading&&<div className="panel-empty">Evaluating candidate portfolio…</div>}
      </section>

      <section className="decision-lower-grid">
        <div className="command-panel why-panel"><div className="panel-title-row"><div><span className="panel-kicker">Why this decision?</span><h2>Decision rationale</h2></div></div><div className="why-list">{candidates.slice(0,4).map((c,index)=>{const d=decisionFor(c.candidate_id,c,recommendation.data);return <article key={c.candidate_id} className={cls(d)}><span>{d==="ADVANCE"?"✓":d==="REJECT"?"×":"◷"}</span><div><strong>{c.display_name}</strong><p>{d==="ADVANCE"?"No definitive blocking failure is present and the current gating evidence supports advancement.":d==="REJECT"?"At least one blocking gate has definitive failing evidence; optimization strengths cannot override it.":"Missing, conflicting, or insufficient evidence prevents a defensible accept/reject outcome."}</p></div></article>})}</div></div>
        <div className="command-panel next-actions-panel"><div className="panel-title-row"><div><span className="panel-kicker">Recommended next actions</span><h2>Close the highest-value gaps</h2></div><span className="count-chip">{actions.data?.length??0}</span></div><div className="action-card-list">{(actions.data??[]).slice(0,7).map(a=><article key={a.action_signature}><span className="action-symbol">⌁</span><div><strong>{a.candidate_display_name??"Programme"}: {a.action_type.replaceAll("_"," ")}</strong><p>{a.reason}</p></div><b className={a.priority>=75?"high":a.priority>=40?"medium":"low"}>{a.priority}</b></article>)}{!actions.isLoading&&(actions.data?.length??0)===0&&<div className="panel-empty">No open scientific actions. Reassess the programme if new evidence has arrived.</div>}</div></div>
      </section>

      <section className="command-panel decision-method"><div className="decision-flow-horizontal">{[["Define","Mission & context"],["Screen","Candidate portfolio"],["Test","Generate evidence"],["Decide","Evaluate gates"],["Act","Run next action"]].map(([a,b],i)=><div key={a} className={i===3?"active":""}><span>{i+1}</span><strong>{a}</strong><small>{b}</small>{i<4&&<i>→</i>}</div>)}</div><div className="decision-summary"><span>DECISION OUTCOME</span><strong>{recommendation.data?.rationale||"TinkerLab keeps failed, unresolved, and advancing candidates separate so the decision remains defensible."}</strong></div></section>
    </>}
  </div>;
}
