"use client";

import Link from "next/link";
import {useCallback, useEffect, useMemo, useState} from "react";
import {api, type ProjectSummary} from "@/lib/api";
import {ActionPriorityBadge} from "@/components/ActionPriorityBadge";

type Program={id:string;name:string;project_id:string;status:string};
type Action={
  id?:string; action_signature:string; candidate_id?:string|null; candidate_display_name?:string|null;
  requirement_id?:string|null; requirement_key?:string|null; action_type:string; status:string; priority:number;
  priority_factors:Record<string,unknown>; decision_value_class:string; cost_class:string; reason:string;
  what_it_could_resolve?:string|null; depends_on:string[]; resolves_gap_kind?:string|null;
};
type Gap={gap_id:string;candidate_id:string;candidate_display_name:string;requirement_id?:string|null;requirement_key?:string|null;display_name?:string|null;gap_class:string;why_unresolved:string;what_would_resolve_it:string;criticality?:string;is_gating?:boolean};
type ProgramGaps={by_candidate:Record<string,Gap[]>;by_class:Record<string,Gap[]>;note:string};
type ActionChanges={created:string[];updated:string[];superseded:string[]};
type ReassessResponse={program_id:string;action_changes:ActionChanges;program_state:{status?:string;reason?:string;reason_codes?:string[]};convergence?:{convergence_state?:string;presentation_progress_percent?:number}};
type RecommendationResponse={recommendation_id?:string;version?:number;decision_delta_id?:string|null;status:string;rationale?:string;qualification_note?:string};
type DecisionDelta={
  id:string;previous_recommendation_id:string;new_recommendation_id:string;previous_status:string;new_status:string;
  changed_requirements:Array<Record<string,unknown>>;new_evidence:Array<{kind?:string;gap_id?:string}>;
  invalidated_evidence:Array<{kind?:string;gap_id?:string}>;changed_ranking:Array<{candidate_id?:string;from_rank?:number|null;to_rank?:number|null}>;
  changed_blockers:Array<{candidate_id?:string;requirement_id?:string;change?:string}>;reason_codes:string[];explanation:string;created_at:string;
};
type DecisionDeltaResponse={program_id:string;deltas:DecisionDelta[];methodology_version:string};
type ImpactRun={reassess:ReassessResponse;recommendation:RecommendationResponse;delta:DecisionDelta|null;completedAt:string};

const terminalActions=new Set(["advance_candidate","reject_candidate","no_action_required"]);

function routeFor(action:Action,projectId:string){
  const t=action.action_type;
  if(t==="run_property_prediction") return {href:`/projects/${projectId}/prediction-lab`,label:"Open Prediction Lab",kind:"computed prediction"};
  if(t==="run_physics_simulation"||t==="run_additional_simulation") return {href:`/projects/${projectId}/virtual-lab`,label:"Open Virtual Lab",kind:"model/simulation"};
  if(t==="create_experiment_plan"||t==="run_experiment"||t==="run_additional_replicate"||t==="run_control") return {href:`/projects/${projectId}/validation`,label:"Open Scientific Validation",kind:"physical experiment"};
  if(t==="add_industrial_evidence"||t==="check_regulation"||t==="check_supply") return {href:`/projects/${projectId}/industrial`,label:"Open Industrial Viability",kind:"industrial evidence"};
  if(t==="resolve_material_state"||t==="collect_reference_data"||t==="investigate_conflict") return {href:`/projects/${projectId}`,label:"Open Evidence Workspace",kind:"evidence review"};
  return {href:`/projects/${projectId}/replacement`,label:"Open Mission Control",kind:"decision record"};
}

function n(value:unknown){return typeof value==="number"?value:null}
function factor(action:Action,key:string){return n(action.priority_factors?.[key])}
function percent(value:number|null){return value===null?"—":`${Math.round(value*100)}%`}
function statusText(value:string|undefined){return (value??"unknown").replaceAll("_"," ")}

export default function ValidationPlanPage(){
  const [projects,setProjects]=useState<ProjectSummary[]>([]);
  const [projectId,setProjectId]=useState("");
  const [programs,setPrograms]=useState<Program[]>([]);
  const [programId,setProgramId]=useState("");
  const [actions,setActions]=useState<Action[]>([]);
  const [gaps,setGaps]=useState<ProgramGaps|null>(null);
  const [deltas,setDeltas]=useState<DecisionDelta[]>([]);
  const [impactRun,setImpactRun]=useState<ImpactRun|null>(null);
  const [loading,setLoading]=useState(true);
  const [reassessing,setReassessing]=useState(false);
  const [error,setError]=useState("");

  useEffect(()=>{
    api<ProjectSummary[]>("/replacement-projects").then(rows=>{setProjects(rows);if(rows[0])setProjectId(rows[0].id)}).catch(e=>setError(e instanceof Error?e.message:"Could not load replacement projects.")).finally(()=>setLoading(false));
  },[]);

  useEffect(()=>{
    if(!projectId){setPrograms([]);setProgramId("");return;}
    setError("");setImpactRun(null);
    api<Program[]>(`/replacement-programs?project_id=${encodeURIComponent(projectId)}`).then(rows=>{setPrograms(rows);setProgramId(rows[0]?.id??"")}).catch(e=>setError(e instanceof Error?e.message:"Could not load replacement programmes."));
  },[projectId]);

  const loadPlan=useCallback(async()=>{
    if(!programId){setActions([]);setGaps(null);setDeltas([]);return;}
    const [a,g,d]=await Promise.all([
      api<Action[]>(`/replacement-programs/${programId}/actions?status=open`),
      api<ProgramGaps>(`/replacement-programs/${programId}/evidence-gaps`),
      api<DecisionDeltaResponse>(`/replacement-programs/${programId}/decision-deltas`),
    ]);
    setActions(a);setGaps(g);setDeltas(d.deltas??[]);
  },[programId]);

  useEffect(()=>{
    if(!programId){setActions([]);setGaps(null);setDeltas([]);return;}
    setLoading(true);setError("");setImpactRun(null);
    loadPlan().catch(e=>setError(e instanceof Error?e.message:"Could not build validation plan.")).finally(()=>setLoading(false));
  },[programId,loadPlan]);

  async function reassessAndRecordImpact(){
    if(!programId||reassessing)return;
    setReassessing(true);setError("");
    try{
      // Reassessment is deterministic and only consumes evidence already accepted by the controlled
      // workflows. Persisting a recommendation afterwards creates the immutable DecisionDelta audit
      // record; it does not invent, import, or reinterpret evidence.
      const reassess=await api<ReassessResponse>(`/replacement-programs/${programId}/reassess`,{method:"POST"});
      const recommendation=await api<RecommendationResponse>(`/replacement-programs/${programId}/recommendation`,{method:"POST",body:JSON.stringify({})});
      const deltaPayload=await api<DecisionDeltaResponse>(`/replacement-programs/${programId}/decision-deltas`);
      await loadPlan();
      const delta=recommendation.decision_delta_id?deltaPayload.deltas.find(d=>d.id===recommendation.decision_delta_id)??null:null;
      setDeltas(deltaPayload.deltas??[]);
      setImpactRun({reassess,recommendation,delta,completedAt:new Date().toISOString()});
    }catch(e){
      setError(e instanceof Error?e.message:"Could not reassess and record decision impact.");
    }finally{setReassessing(false)}
  }

  const ready=useMemo(()=>actions.filter(a=>a.status==="ready"&&!terminalActions.has(a.action_type)).sort((a,b)=>b.priority-a.priority),[actions]);
  const blocked=useMemo(()=>actions.filter(a=>a.status==="blocked"&&!terminalActions.has(a.action_type)).sort((a,b)=>b.priority-a.priority),[actions]);
  const top=ready.slice(0,5);
  const selectedProject=projects.find(p=>p.id===projectId);
  const selectedProgram=programs.find(p=>p.id===programId);
  const gapCount=gaps?Object.values(gaps.by_class).reduce((sum,rows)=>sum+rows.length,0):0;
  const candidateCount=new Set(actions.map(a=>a.candidate_id).filter(Boolean)).size;
  const latestDelta=impactRun?.delta??deltas[0]??null;

  return <div className="workspace-page">
    <div className="workspace-hero compact"><div><span className="workspace-kicker">Decision-impact validation planning</span><h1>Resolve the evidence that can actually change the decision.</h1><p>TinkerLab converts unresolved requirements into a deterministic, dependency-aware action queue, then records exactly what changed after accepted evidence is reassessed. Priority is decision impact × decision value × candidate relevance ÷ declared effort class—not a probability of success or fabricated information gain.</p></div></div>

    <section className="command-panel" style={{marginBottom:20}}>
      <div className="panel-title-row"><div><span className="panel-kicker">Programme scope</span><h2>Select the replacement mission to validate</h2></div><span className="count-chip">evidence-controlled workflow</span></div>
      <div style={{display:"flex",gap:12,alignItems:"end",flexWrap:"wrap"}}>
        <label style={{minWidth:300}}><small>Replacement project</small><select value={projectId} onChange={e=>setProjectId(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label style={{minWidth:300}}><small>Decision programme</small><select value={programId} onChange={e=>setProgramId(e.target.value)} disabled={!programs.length}>{programs.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        {projectId&&<Link className="btn btn-secondary" href={`/projects/${projectId}/replacement`}>Open Mission Control</Link>}
      </div>
      <p className="muted" style={{marginTop:12}}>Planning never starts a prediction, simulation, experiment, supplier check, or regulatory check. Evidence must first enter through its controlled workflow. Reassessment only consumes evidence already accepted by TinkerLab.</p>
      {error&&<div className="panel-empty"><strong>Validation plan unavailable.</strong><p>{error}</p></div>}
    </section>

    {loading?<div className="command-panel panel-empty">Building evidence-resolution plan…</div>:programId&&<>
      <section className="decision-outcome-kpis" style={{marginBottom:20}}>
        <article className="advance"><small>Ready now</small><strong>{ready.length}</strong><span>Unblocked scientific actions</span></article>
        <article className="hold"><small>Waiting</small><strong>{blocked.length}</strong><span>Dependency-blocked actions</span></article>
        <article className="neutral"><small>Evidence gaps</small><strong>{gapCount}</strong><span>Explicit unresolved requirements</span></article>
        <article className="neutral"><small>Decision deltas</small><strong>{deltas.length}</strong><span>Persisted recommendation changes</span></article>
      </section>

      <section className="command-panel" style={{marginBottom:20}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Closed-loop reassessment</span><h2>After evidence arrives, prove what it changed</h2></div><span className="count-chip">deterministic + versioned</span></div>
        <p>When a controlled prediction, simulation, experiment, industrial check, or evidence review has finished and its result is already stored, reassess the mission. TinkerLab recomputes the action queue and convergence state, supersedes obsolete actions, persists a new recommendation version, and records an immutable decision delta against the previous recommendation.</p>
        <div style={{display:"flex",gap:12,alignItems:"center",flexWrap:"wrap",marginTop:14}}>
          <button className="btn" type="button" disabled={reassessing} onClick={reassessAndRecordImpact}>{reassessing?"Reassessing evidence…":"Reassess & record decision impact"}</button>
          <span className="muted">This does not create evidence, run a model, or start an experiment.</span>
        </div>
        {impactRun&&<div className="grid grid-2" style={{marginTop:16}}>
          <div className="card card-pad"><div className="eyebrow">Action queue impact</div><h3>{impactRun.reassess.action_changes.superseded.length} superseded · {impactRun.reassess.action_changes.created.length} new</h3><p className="muted">{impactRun.reassess.action_changes.updated.length} existing action(s) updated. Programme state: <strong>{statusText(impactRun.reassess.program_state?.status)}</strong>.</p><p>{impactRun.reassess.program_state?.reason??"State was recomputed from current evidence."}</p></div>
          <div className="card card-pad"><div className="eyebrow">Recommendation impact</div><h3>v{impactRun.recommendation.version??"—"} · {statusText(impactRun.recommendation.status)}</h3><p>{impactRun.recommendation.rationale??"Recommendation persisted from the current evidence state."}</p><div className="muted">Decision delta: {impactRun.recommendation.decision_delta_id??"first recommendation — no prior version to compare"}</div></div>
        </div>}
      </section>

      {latestDelta&&<section className="command-panel" style={{marginBottom:20}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Decision-change explanation</span><h2>{statusText(latestDelta.previous_status)} → {statusText(latestDelta.new_status)}</h2></div><span className="count-chip">{latestDelta.reason_codes.length} reason code(s)</span></div>
        <p>{latestDelta.explanation}</p>
        <div className="decision-outcome-kpis" style={{margin:"16px 0"}}>
          <article className="advance"><small>Gaps closed</small><strong>{latestDelta.new_evidence.length}</strong><span>No longer open in the new recommendation</span></article>
          <article className="hold"><small>Gaps opened/reopened</small><strong>{latestDelta.invalidated_evidence.length}</strong><span>Evidence invalidated or requirement changed</span></article>
          <article className="neutral"><small>Blocker changes</small><strong>{latestDelta.changed_blockers.length}</strong><span>Added or cleared gating blockers</span></article>
          <article className="neutral"><small>Rank changes</small><strong>{latestDelta.changed_ranking.length}</strong><span>Deterministic order changes</span></article>
        </div>
        {(latestDelta.changed_blockers.length>0||latestDelta.changed_ranking.length>0)&&<div className="table-wrap"><table><thead><tr><th>Change</th><th>Candidate</th><th>Detail</th></tr></thead><tbody>
          {latestDelta.changed_blockers.map((row,i)=><tr key={`b-${i}`}><td>{statusText(row.change)}</td><td>{row.candidate_id??"—"}</td><td>{row.requirement_id?`Requirement ${row.requirement_id}`:"Gating blocker changed"}</td></tr>)}
          {latestDelta.changed_ranking.map((row,i)=><tr key={`r-${i}`}><td>rank changed</td><td>{row.candidate_id??"—"}</td><td>{row.from_rank??"unranked"} → {row.to_rank??"unranked"}</td></tr>)}
        </tbody></table></div>}
        <p className="muted" style={{marginTop:12}}>A “gap closed” entry means the gap present in the previous persisted recommendation is absent from the new one. The delta does not relabel a computed result as an experiment and does not infer causality beyond the stored recommendation/evidence state.</p>
      </section>}

      <section className="command-panel" style={{marginBottom:20}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Smallest useful next programme</span><h2>{selectedProgram?.name||selectedProject?.name||"Validation plan"}</h2></div><span className="count-chip">top {top.length} ready actions</span></div>
        <p className="muted">Start with the highest-ranked ready action, then reassess the mission after new evidence arrives. Do not execute every item blindly: a single decisive result can supersede later work.</p>
        <div style={{display:"grid",gap:14}}>{top.map((action,index)=>{const route=routeFor(action,projectId);const impact=factor(action,"decision_impact"),value=factor(action,"decision_value"),relevance=factor(action,"candidate_relevance"),cost=factor(action,"cost_factor");return <article className="card card-pad" key={action.id??action.action_signature}>
          <div className="topline" style={{marginBottom:10,alignItems:"center"}}><div><div className="eyebrow">Step {index+1} · {route.kind}</div><h3>{action.action_type.replaceAll("_"," ")}</h3><div className="muted">{action.candidate_display_name??action.candidate_id??"programme"}{action.requirement_key?` · ${action.requirement_key}`:""}</div></div><ActionPriorityBadge priority={action.priority} factors={action.priority_factors}/></div>
          <p>{action.reason}</p>{action.what_it_could_resolve&&<p><strong>Decision impact:</strong> {action.what_it_could_resolve}</p>}
          <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"10px 0"}}><span className="badge">impact {percent(impact)}</span><span className="badge">decision value {percent(value)}</span><span className="badge">candidate relevance {percent(relevance)}</span><span className="badge">effort factor {cost??"—"}</span><span className="badge">{action.cost_class} effort class</span></div>
          <Link className="btn" href={route.href}>{route.label}</Link>
        </article>})}{!top.length&&<div className="panel-empty">No unblocked evidence-collection action is currently recommended. Review blocked dependencies or the mission conclusion.</div>}</div>
      </section>

      {blocked.length>0&&<section className="command-panel" style={{marginBottom:20}}><div className="panel-title-row"><div><span className="panel-kicker">Dependency protection</span><h2>Work that should not start yet</h2></div><span className="count-chip">{blocked.length} blocked</span></div><p className="muted">These actions remain visible so the plan is auditable, but TinkerLab prevents them from looking executable before prerequisite evidence work is resolved.</p><div className="table-wrap"><table><thead><tr><th>Action</th><th>Candidate</th><th>Requirement</th><th>Blocked by</th><th>Priority</th></tr></thead><tbody>{blocked.map(a=><tr key={a.id??a.action_signature}><td>{a.action_type.replaceAll("_"," ")}</td><td>{a.candidate_display_name??a.candidate_id??"—"}</td><td>{a.requirement_key??"—"}</td><td>{a.depends_on.length} prerequisite(s)</td><td><ActionPriorityBadge priority={a.priority} factors={a.priority_factors}/></td></tr>)}</tbody></table></div></section>}

      <section className="command-panel"><div className="panel-title-row"><div><span className="panel-kicker">Scientific boundary</span><h2>What this plan does—and does not—mean</h2></div></div><p>Predictions remain model outputs, simulations remain simulated evidence, reference/database values remain source evidence, and physical measurements remain experimental evidence. A cheaper computational action can reduce uncertainty or screen a candidate, but it does not become a measurement and cannot satisfy a policy that explicitly requires experimental validation.</p><p className="muted">The priority factors are declared effort and decision-value classes. They are not laboratory cost estimates, success probabilities, Bayesian expected value of information, or qualification confidence. Decision deltas describe changes between persisted recommendation versions; they do not manufacture a causal scientific claim.</p></section>
    </>}
  </div>;
}
