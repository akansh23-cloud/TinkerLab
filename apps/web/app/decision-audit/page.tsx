"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {api,ProjectSummary,ReplacementProgramRecord,ReplacementRecommendationRecord,ScientificActionRecord,TimelineEventRecord} from "@/lib/api";

type AuditAction = ScientificActionRecord & {result_reference?:string|null;started_at?:string|null;completed_at?:string|null};
type DecisionDelta = {
  id:string;previous_recommendation_id:string;new_recommendation_id:string;
  previous_status:string;new_status:string;changed_requirements:Array<Record<string,unknown>>;
  new_evidence:Array<{kind?:string;gap_id?:string}>;invalidated_evidence:Array<{kind?:string;gap_id?:string}>;
  changed_ranking:Array<{candidate_id?:string;from_rank?:number|null;to_rank?:number|null}>;
  changed_blockers:Array<{candidate_id?:string;requirement_id?:string;change?:string}>;
  reason_codes:string[];explanation:string;created_at:string;
};
type DecisionDeltaResponse={program_id:string;deltas:DecisionDelta[];methodology_version:string};

type AuditRow={
  action:AuditAction;event?:TimelineEventRecord;candidateName:string;
  sourceClass:string;reference:string;completedAt?:string;
};

function sourceClass(actionType:string,reference?:string|null){
  const ref=(reference??"").toLowerCase();
  const type=actionType.toLowerCase();
  if(ref.startsWith("property_prediction:")||type.includes("prediction")) return "PREDICTED";
  if(ref.startsWith("simulation")||type.includes("simulation")) return "SIMULATED";
  if(ref.startsWith("experimental_measurements:")||type.includes("experiment")||type.includes("replicate")||type.includes("control")) return "MEASURED";
  if(ref.startsWith("industrial_viability_assessment:")||type.includes("industrial")||type.includes("regulation")||type.includes("supply")) return "INDUSTRIAL";
  return "OTHER";
}
function human(s:string){return s.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase())}
function shortRef(s?:string|null){if(!s)return "No immutable result reference recorded";return s.length>76?`${s.slice(0,73)}…`:s}
function time(s?:string|null){if(!s)return "—";const d=new Date(s);return Number.isNaN(d.getTime())?s:d.toLocaleString()}

export default function DecisionAuditWorkspace(){
  const projects=useQuery({queryKey:["audit-projects"],queryFn:()=>api<ProjectSummary[]>("/replacement-projects")});
  const [projectId,setProjectId]=useState("");
  const [programChoice,setProgramChoice]=useState("");
  useEffect(()=>{if(!projectId&&projects.data?.[0]?.id)setProjectId(projects.data[0].id)},[projects.data,projectId]);
  const programs=useQuery({queryKey:["audit-programs",projectId],enabled:!!projectId,queryFn:()=>api<ReplacementProgramRecord[]>(`/replacement-programs?project_id=${encodeURIComponent(projectId)}`)});
  const programId=programChoice||programs.data?.[0]?.id||"";
  useEffect(()=>{if(programChoice&&programs.data&&!programs.data.some(p=>p.id===programChoice))setProgramChoice("")},[programChoice,programs.data]);

  const actions=useQuery({queryKey:["audit-actions",programId],enabled:!!programId,queryFn:()=>api<AuditAction[]>(`/replacement-programs/${programId}/actions`)});
  const timeline=useQuery({queryKey:["audit-timeline",programId],enabled:!!programId,queryFn:()=>api<TimelineEventRecord[]>(`/replacement-programs/${programId}/timeline?limit=300`)});
  const deltas=useQuery({queryKey:["audit-deltas",programId],enabled:!!programId,queryFn:()=>api<DecisionDeltaResponse>(`/replacement-programs/${programId}/decision-deltas`)});
  const recommendations=useQuery({queryKey:["audit-recommendations",programId],enabled:!!programId,queryFn:()=>api<ReplacementRecommendationRecord[]>(`/replacement-programs/${programId}/recommendations`)});

  const activeProject=projects.data?.find(p=>p.id===projectId);
  const candidateNames=useMemo(()=>{
    const map=new Map<string,string>();
    for(const a of actions.data??[]) if(a.candidate_id&&a.candidate_display_name) map.set(a.candidate_id,a.candidate_display_name);
    return map;
  },[actions.data]);
  const eventByAction=useMemo(()=>{
    const map=new Map<string,TimelineEventRecord>();
    for(const e of timeline.data??[]) if(e.reference_kind==="scientific_action"&&e.reference_id) {
      const previous=map.get(e.reference_id);
      if(!previous||new Date(e.occurred_at).getTime()>new Date(previous.occurred_at).getTime()) map.set(e.reference_id,e);
    }
    return map;
  },[timeline.data]);
  const completedRows=useMemo<AuditRow[]>(()=>
    (actions.data??[])
      .filter(a=>a.status==="completed"||!!a.result_reference)
      .map(a=>({
        action:a,event:a.id?eventByAction.get(a.id):undefined,
        candidateName:a.candidate_display_name??(a.candidate_id?candidateNames.get(a.candidate_id):undefined)??"Programme",
        sourceClass:sourceClass(a.action_type,a.result_reference),reference:a.result_reference??"",
        completedAt:a.completed_at??(a.id?eventByAction.get(a.id)?.occurred_at:undefined)??a.created_at,
      }))
      .sort((a,b)=>new Date(b.completedAt??0).getTime()-new Date(a.completedAt??0).getTime()),
    [actions.data,eventByAction,candidateNames]
  );
  const sourceCounts=useMemo(()=>completedRows.reduce<Record<string,number>>((acc,row)=>{acc[row.sourceClass]=(acc[row.sourceClass]??0)+1;return acc},{}),[completedRows]);
  const recById=useMemo(()=>new Map((recommendations.data??[]).map(r=>[r.id??r.recommendation_id??"",r])),[recommendations.data]);

  return <div className="workspace-page">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Result → Evidence → Decision</span><h1>Decision audit trail</h1><p>Trace completed prediction, simulation, physical-validation and industrial work into immutable result references, gap changes, blockers and recommendation versions.</p></div>
      <div className="hero-actions"><Link className="btn btn-secondary" href="/decisions">Decision workspace</Link>{projectId&&<Link className="btn" href={`/projects/${projectId}/replacement`}>Mission Control</Link>}</div>
    </div>

    <div className="notice"><strong>Audit boundary</strong><div className="muted">This view reports persisted records only. A result reference proves that a controlled workflow completed an action; a Decision Delta proves what changed between recommendation versions. When the database does not persist a direct causal link between the two, TinkerLab does not invent one.</div></div>

    <div className="decision-selector command-panel">
      <label><small>Replacement mission</small><select value={projectId} onChange={e=>{setProjectId(e.target.value);setProgramChoice("")}}>{(projects.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label><small>Decision programme</small><select value={programId} onChange={e=>setProgramChoice(e.target.value)}>{(programs.data??[]).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <div className="selector-context"><span>INCUMBENT</span><strong>{activeProject?.baseline_material.display_name??"—"}</strong><small>{activeProject?.constraint_count??0} declared requirements</small></div>
    </div>

    {programId&&<>
      <section className="decision-outcome-kpis">
        <article className="neutral"><small>Completed evidence actions</small><strong>{completedRows.length}</strong><span>With persisted workflow state</span></article>
        <article className="advance"><small>Measured</small><strong>{sourceCounts.MEASURED??0}</strong><span>Physical validation references</span></article>
        <article className="hold"><small>Computed</small><strong>{(sourceCounts.PREDICTED??0)+(sourceCounts.SIMULATED??0)}</strong><span>Prediction + simulation references</span></article>
        <article className="neutral"><small>Decision deltas</small><strong>{deltas.data?.deltas.length??0}</strong><span>Persisted recommendation changes</span></article>
      </section>

      <section className="command-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Immutable result ledger</span><h2>Which controlled workflow produced which decision input?</h2></div><span className="count-chip">{completedRows.length}</span></div>
        <div className="table-wrap"><table><thead><tr><th>Evidence class</th><th>Candidate</th><th>Completed action</th><th>Immutable result reference</th><th>Completed</th></tr></thead><tbody>
          {completedRows.map((row,i)=><tr key={row.action.id??`${row.action.action_signature}-${i}`}>
            <td><span className="badge">{row.sourceClass}</span></td>
            <td><strong>{row.candidateName}</strong>{row.action.requirement_key&&<div className="muted">Requirement: {row.action.requirement_key}</div>}</td>
            <td>{human(row.action.action_type)}<div className="muted">{row.action.reason_code}</div></td>
            <td><code style={{fontSize:11,wordBreak:"break-all"}}>{shortRef(row.reference)}</code>{row.event&&<div className="muted">Timeline: {row.event.summary}</div>}</td>
            <td className="muted">{time(row.completedAt)}</td>
          </tr>)}
          {!actions.isLoading&&completedRows.length===0&&<tr><td colSpan={5}><div className="panel-empty">No completed scientific actions with persisted result state are available for this programme yet.</div></td></tr>}
        </tbody></table></div>
      </section>

      <section className="command-panel" style={{marginTop:16}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Recommendation change ledger</span><h2>What changed after evidence was reassessed?</h2></div><span className="count-chip">{deltas.data?.deltas.length??0}</span></div>
        <div className="grid" style={{gap:12}}>{(deltas.data?.deltas??[]).map(delta=>{
          const from=recById.get(delta.previous_recommendation_id);const to=recById.get(delta.new_recommendation_id);
          return <article className="notice" key={delta.id} style={{margin:0}}>
            <div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"flex-start"}}><div><strong>{delta.previous_status} → {delta.new_status}</strong><div className="muted">Recommendation v{from?.version??"?"} → v{to?.version??"?"} · {time(delta.created_at)}</div></div><span className="badge">{delta.reason_codes.length} change code{delta.reason_codes.length===1?"":"s"}</span></div>
            <p className="muted" style={{marginTop:8}}>{delta.explanation}</p>
            <div className="grid grid-2" style={{marginTop:8}}>
              <div><strong>Evidence gaps</strong><div className="muted">Closed: {delta.new_evidence.length} · Opened/reopened: {delta.invalidated_evidence.length}</div>{delta.new_evidence.slice(0,4).map((e,i)=><div className="muted" key={i}>✓ {e.gap_id??e.kind}</div>)}{delta.invalidated_evidence.slice(0,4).map((e,i)=><div className="muted" key={`r-${i}`}>↺ {e.gap_id??e.kind}</div>)}</div>
              <div><strong>Decision impact</strong><div className="muted">Blocker changes: {delta.changed_blockers.length} · Rank changes: {delta.changed_ranking.length} · Candidate-state changes: {delta.changed_requirements.length}</div>{delta.changed_blockers.slice(0,4).map((b,i)=><div className="muted" key={i}>{String(b.change??"BLOCKER_CHANGE")}: {String(b.requirement_id??"requirement")} · candidate {String(b.candidate_id??"—")}</div>)}</div>
            </div>
          </article>})}
          {!deltas.isLoading&&(deltas.data?.deltas.length??0)===0&&<div className="panel-empty">No persisted Decision Delta exists yet. Generate a recommendation, add or invalidate evidence, then generate the next recommendation version to create an immutable before/after record.</div>}
        </div>
      </section>

      <section className="command-panel" style={{marginTop:16}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Event provenance</span><h2>Latest programme events</h2></div><span className="count-chip">{timeline.data?.length??0}</span></div>
        <div className="table-wrap"><table><thead><tr><th>Time</th><th>Event</th><th>Candidate</th><th>Reference</th></tr></thead><tbody>{(timeline.data??[]).slice(0,25).map(e=><tr key={e.id}><td className="muted">{time(e.occurred_at)}</td><td><strong>{human(e.event_kind)}</strong><div className="muted">{e.summary}</div></td><td>{e.candidate_id?candidateNames.get(e.candidate_id)??e.candidate_id:"Programme"}</td><td><code style={{fontSize:11}}>{e.reference_kind&&e.reference_id?`${e.reference_kind}:${e.reference_id}`:"—"}</code></td></tr>)}</tbody></table></div>
      </section>
    </>}
  </div>;
}
