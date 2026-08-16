"use client";

import {use, useMemo, useState} from "react";
import Link from "next/link";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {
  api, CandidateLabItem, CandidatePage, ExperimentPlanRecord, ExperimentRunRecord,
  MeasurementRecord, ReasoningRole, RecommendationResponse, ReplacementDecisionRecord,
  SampleRecord, ValidationResultRecord,
} from "@/lib/api";
import {ValidationStateBadge} from "@/components/ValidationStateBadge";
import {MeasurementQualityBadge} from "@/components/MeasurementQualityBadge";
import {OriginBadge} from "@/components/OriginBadge";

const OUTCOME_LABELS:Record<string,string>={
  EXPERIMENT_SUPPORTS_REQUIREMENT:"Supports requirement",
  EXPERIMENT_CONTRADICTS_REQUIREMENT:"Contradicts requirement",
  EXPERIMENT_INCONCLUSIVE:"Inconclusive",
  EXPERIMENT_CONFLICTING:"Conflicting experiments",
  EXPERIMENT_NOT_AVAILABLE:"Not experimentally tested",
};

type ProtocolRecord={id:string;key:string;display_name:string;objective?:string;property_definition_id?:string;versions:Array<{
  id:string;version:string;protocol_checksum:string;is_frozen:boolean;superseded_by_id?:string;
  replicate_requirement:number;control_requirement?:string;created_at:string;
}>};
type InstrumentRecord={id:string;key:string;display_name:string;measures_property_keys:string[];calibration_status:string;calibration_due_date?:string};
type ReplacementProgram={id:string;project_id:string};
type DecisionAction={id:string;candidate_id?:string|null;requirement_id?:string|null;requirement_key?:string|null;action_type:string;status:string};
type DecisionSync={completed:number;eligible:number;measurementCount:number;note:string};

const DECISIVE_EXPERIMENTAL_OUTCOMES=new Set(["EXPERIMENT_SUPPORTS_REQUIREMENT","EXPERIMENT_CONTRADICTS_REQUIREMENT"]);
const EXPERIMENT_ACTION_TYPES=new Set(["run_experiment","run_additional_replicate","run_control"]);

function targetOf(candidate:CandidateLabItem|undefined){
  if(!candidate) return null;
  return candidate.candidate_kind==="known_material"?candidate.material_id:candidate.hypothesis_id;
}

export default function CandidateValidationPage({params}:{params:Promise<{id:string}>}){
  const {id}=use(params); const qc=useQueryClient();
  const candidates=useQuery({queryKey:["candidate-lab",id],queryFn:()=>api<CandidatePage>(`/replacement-projects/${id}/candidate-lab?offset=0&limit=200`)});
  const roles=useQuery({queryKey:["reasoning-roles"],queryFn:()=>api<ReasoningRole[]>("/reasoning/roles")});
  const protocols=useQuery({queryKey:["experiment-protocols"],queryFn:()=>api<ProtocolRecord[]>("/experiments/protocols")});
  const instruments=useQuery({queryKey:["experiment-instruments"],queryFn:()=>api<InstrumentRecord[]>("/experiments/instruments")});
  const [candidateChoice,setCandidateChoice]=useState("");
  const [roleChoice,setRoleChoice]=useState("");
  const candidateId=candidateChoice||candidates.data?.items[0]?.id||"";
  const roleId=roleChoice||roles.data?.[0]?.id||"";
  const candidate=candidates.data?.items.find(c=>c.id===candidateId);

  const validation=useQuery({queryKey:["candidate-validation",id,candidateId,roleId],enabled:!!candidateId&&!!roleId,
    queryFn:()=>api<ValidationResultRecord>("/experiments/validation/assess",{method:"POST",body:JSON.stringify({role_id:roleId,candidate_id:candidateId,project_id:id,persist:false})})});
  const recommendations=useQuery({queryKey:["candidate-recommendations",id,candidateId,roleId],enabled:!!candidateId&&!!roleId,
    queryFn:()=>api<RecommendationResponse>("/experiments/recommendations",{method:"POST",body:JSON.stringify({role_id:roleId,candidate_id:candidateId,project_id:id,persist:false})})});
  const decision=useQuery({queryKey:["replacement-decision",id,candidateId,roleId],enabled:!!candidateId&&!!roleId,
    queryFn:()=>api<ReplacementDecisionRecord>("/experiments/replacement-decision",{method:"POST",body:JSON.stringify({role_id:roleId,candidate_id:candidateId,persist_validation:false})})});
  const samples=useQuery({queryKey:["candidate-samples",candidateId],enabled:!!candidateId,
    queryFn:()=>api<SampleRecord[]>(`/experiments/samples?candidate_id=${encodeURIComponent(candidateId)}&limit=200`)});
  const plans=useQuery({queryKey:["candidate-plans",candidateId],enabled:!!candidateId,
    queryFn:()=>api<ExperimentPlanRecord[]>(`/experiments/plans?candidate_id=${encodeURIComponent(candidateId)}&limit=200`)});
  const runs=useQuery({queryKey:["candidate-runs",candidateId],enabled:!!candidateId,
    queryFn:()=>api<ExperimentRunRecord[]>(`/experiments/runs?candidate_id=${encodeURIComponent(candidateId)}&limit=200`)});
  const measurements=useQuery({queryKey:["candidate-measurements",candidateId],enabled:!!candidateId,
    queryFn:()=>api<MeasurementRecord[]>(`/experiments/measurements?candidate_id=${encodeURIComponent(candidateId)}&limit=200`)});

  const [selectedSample,setSelectedSample]=useState("");
  const [selectedInstrument,setSelectedInstrument]=useState("");
  const [invalidationReason,setInvalidationReason]=useState("Documented run validity issue discovered after execution");
  const [decisionSync,setDecisionSync]=useState<DecisionSync|null>(null);
  const [decisionSyncError,setDecisionSyncError]=useState("");
  const selectedSampleId=selectedSample||samples.data?.find(s=>s.provenance_complete)?.id||samples.data?.[0]?.id||"";
  const selectedInstrumentId=selectedInstrument||instruments.data?.find(i=>i.calibration_status==="calibrated")?.id||instruments.data?.[0]?.id||"";

  async function closeExperimentalDecisionActions(completedRun:ExperimentRunRecord){
    setDecisionSync(null);setDecisionSyncError("");
    if(completedRun.status!=="completed") return;
    try{
      const [freshPlans,freshMeasurements,assessment]=await Promise.all([
        api<ExperimentPlanRecord[]>(`/experiments/plans?candidate_id=${encodeURIComponent(candidateId)}&limit=200`),
        api<MeasurementRecord[]>(`/experiments/measurements?candidate_id=${encodeURIComponent(candidateId)}&limit=200`),
        api<ValidationResultRecord>("/experiments/validation/assess",{method:"POST",body:JSON.stringify({role_id:roleId,candidate_id:candidateId,project_id:id,persist:false})}),
      ]);
      const plan=freshPlans.find(p=>p.id===completedRun.plan_id);
      if(!plan?.requirement_id){
        setDecisionSync({completed:0,eligible:0,measurementCount:0,note:"Completed run has no requirement-bound experiment plan, so no decision action was closed."});
        return;
      }
      const propertyResult=assessment.per_property_comparisons.find(r=>r.requirement_id===plan.requirement_id);
      if(!propertyResult||!DECISIVE_EXPERIMENTAL_OUTCOMES.has(propertyResult.experimental_outcome)){
        setDecisionSync({completed:0,eligible:0,measurementCount:0,note:"The completed run did not produce a decisive admissible experimental outcome. INCONCLUSIVE, CONFLICTING and unavailable results remain open for further validation."});
        return;
      }
      const admissibleIds=new Set(propertyResult.experimental_values.filter(v=>
        (v.admissibility?.toLowerCase()==="admissible"||(v.admissibility_codes??[]).length===0)
      ).map(v=>v.measurement_id));
      const runMeasurements=freshMeasurements.filter(m=>
        m.run_id===completedRun.id&&admissibleIds.has(m.id)&&m.admissibility_codes.length===0&&!['rejected','invalid','invalidated'].includes(m.quality.toLowerCase())
      );
      if(!runMeasurements.length){
        setDecisionSync({completed:0,eligible:0,measurementCount:0,note:"The mission may have older experimental evidence, but this completed run contributed no newly admissible measurement. No action was closed."});
        return;
      }
      const programs=await api<ReplacementProgram[]>(`/replacement-programs?project_id=${encodeURIComponent(id)}`);
      let eligible=0,completed=0;
      const resultReference=`experimental_measurements:${runMeasurements.map(m=>`${m.id}@${m.measurement_checksum}`).join(",")}`;
      for(const program of programs){
        const actions=await api<DecisionAction[]>(`/replacement-programs/${program.id}/actions?status=open`);
        for(const action of actions){
          if(!EXPERIMENT_ACTION_TYPES.has(action.action_type)||action.candidate_id!==candidateId) continue;
          if(action.requirement_id&&action.requirement_id!==plan.requirement_id) continue;
          if(!action.requirement_id&&action.requirement_key&&action.requirement_key!==propertyResult.property_key) continue;
          if(action.action_type==="run_control"&&!completedRun.is_control) continue;
          if(action.action_type!=="run_control"&&completedRun.is_control) continue;
          eligible+=1;
          await api(`/replacement-programs/${program.id}/actions/${action.id}/transition`,{
            method:"POST",
            body:JSON.stringify({
              transition:"complete",
              result_reference:resultReference,
              note:`Closed automatically from completed physical experiment run ${completedRun.id}. Only admissible persisted measurements from this run are referenced; experimental evidence remains distinct from predictions and simulations.`,
            }),
          });
          completed+=1;
        }
      }
      setDecisionSync({completed,eligible,measurementCount:runMeasurements.length,note:completed?"Matching candidate/requirement experiment actions were closed with immutable measurement IDs + checksums. The backend emitted scoped evidence events and reassessed affected conclusions.":"The run produced admissible experimental evidence, but no matching open decision action existed; no action state was changed."});
      await qc.invalidateQueries({queryKey:["replacement-decision",id,candidateId,roleId]});
    }catch(e){
      setDecisionSyncError(e instanceof Error?e.message:"Experiment completed, but decision-loop synchronization failed.");
    }
  }

  const runAction=useMutation({mutationFn:({runId,action}:{runId:string;action:"ready"|"start"|"complete"|"cancel"|"invalidate"})=>
    api<ExperimentRunRecord>(`/experiments/runs/${runId}/${action}${action==="invalidate"?`?reason=${encodeURIComponent(invalidationReason)}`:""}`,{method:"POST"}),
    onSuccess:async(run,variables)=>{await Promise.all([
      qc.invalidateQueries({queryKey:["candidate-runs",candidateId]}),
      qc.invalidateQueries({queryKey:["candidate-measurements",candidateId]}),
      qc.invalidateQueries({queryKey:["candidate-validation",id,candidateId,roleId]}),
      qc.invalidateQueries({queryKey:["replacement-decision",id,candidateId,roleId]}),
    ]);if(variables.action==="complete")await closeExperimentalDecisionActions(run);}});

  const recommendationById=useMemo(()=>new Map((recommendations.data?.recommendations??[]).map(r=>[r.requirement_id,r])),[recommendations.data]);
  const createPlan=useMutation({mutationFn:(requirementId:string)=>{
    const recommendation=recommendationById.get(requirementId);
    const protocol=protocols.data?.find(p=>p.id===recommendation?.suggested_protocol_id);
    const version=protocol?.versions.filter(v=>!v.superseded_by_id).at(-1)??protocol?.versions.at(-1);
    if(!recommendation||!protocol||!version||!selectedSampleId||!selectedInstrumentId) throw new Error("A protocol version, traceable sample and instrument are required before a plan can be created.");
    return api<{plan_id:string}>("/experiments/plans",{method:"POST",body:JSON.stringify({
      display_name:`${candidate?.display_name??"Candidate"} · ${recommendation.requirement_display_name}`,
      objective:`Resolve the evidence gap for ${recommendation.requirement_display_name} using the pinned protocol and traceable specimen.`,
      design_kind:"single_run",protocol_version_id:version.id,factors:[],replicate_count:Math.max(1,version.replicate_requirement),
      control_plan:version.control_requirement?`Required control: ${version.control_requirement}`:null,
      project_id:id,candidate_id:candidateId,role_id:roleId,requirement_id:requirementId,
      sample_id:selectedSampleId,instrument_id:selectedInstrumentId,run_code_prefix:"TLAB",
    })});
  },onSuccess:async()=>{await Promise.all([qc.invalidateQueries({queryKey:["candidate-plans",candidateId]}),qc.invalidateQueries({queryKey:["candidate-runs",candidateId]}),qc.invalidateQueries({queryKey:["candidate-validation",id,candidateId,roleId]})]);}});

  if(candidates.isLoading||roles.isLoading) return <div className="empty">Loading candidate validation workspace…</div>;
  if(candidates.error||!candidates.data) return <div className="empty">Validation workspace unavailable: {(candidates.error as Error)?.message}</div>;
  const result=validation.data;

  return <div className="grid">
    <div className="topline"><div><div className="eyebrow">Scientific Validation · Phase 9.1</div><h1>Candidate evidence → experiment → next-gate decision</h1><div className="muted">The candidate ID is authoritative. Target, project and organisation are derived server-side; measurement existence alone is never treated as requirement support.</div></div><div style={{display:"flex",gap:8}}><Link className="btn btn-secondary" href={`/projects/${id}/industrial`}>Industrial Viability</Link><Link className="btn btn-secondary" href={`/projects/${id}`}>Project</Link></div></div>

    <div className="notice"><strong>Scientific truth boundary</strong><div className="muted">Observed, predicted, simulated, experimental and industrial evidence remain separate. UNKNOWN, NOT COMPARABLE, INCONCLUSIVE and CONFLICTING are preserved rather than guessed away.</div></div>

    {(decisionSync||decisionSyncError)&&<div className={`notice ${decisionSyncError?"fail":""}`}><strong>Decision-loop integration</strong>{decisionSync&&<div><div>{decisionSync.completed}/{decisionSync.eligible} matching experimental action(s) closed · {decisionSync.measurementCount} admissible measurement(s) referenced.</div><div className="muted">{decisionSync.note}</div></div>}{decisionSyncError&&<div className="muted">The physical run remains persisted, but its decision action was deliberately left open because synchronization failed: {decisionSyncError}</div>}</div>}

    <div className="card card-pad"><div className="eyebrow">Decision context</div><div className="grid grid-2">
      <label className="label">Project candidate<select className="select" value={candidateId} onChange={e=>{setCandidateChoice(e.target.value);setSelectedSample("");setDecisionSync(null);setDecisionSyncError("")}}>{candidates.data.items.map(c=><option key={c.id} value={c.id}>{c.display_name} · {c.candidate_kind}</option>)}</select></label>
      <label className="label">Material role<select className="select" value={roleId} onChange={e=>{setRoleChoice(e.target.value);setDecisionSync(null);setDecisionSyncError("")}}>{roles.data?.map(r=><option key={r.id} value={r.id}>{r.application_name} · {r.component_name} · {r.display_name}</option>)}</select></label>
    </div><div className="muted" style={{marginTop:8}}>Candidate target: {candidate?.candidate_kind} · <code>{targetOf(candidate)?.slice(0,16)??"—"}…</code></div></div>

    {decision.data&&<div className="card card-pad"><div className="eyebrow">Replacement decision gate</div><h2>{decision.data.decision}</h2><div className="muted">Experimental: {decision.data.experimental_status} · Industrial: {decision.data.industrial_status} · Method {decision.data.methodology_version}</div><p>{decision.data.qualification_note}</p>{decision.data.reason_codes.length>0&&<div className="notice"><strong>Reason codes</strong><div className="muted">{decision.data.reason_codes.join(" · ")}</div></div>}{decision.data.blocking_requirements.length>0&&<div className="notice fail" style={{marginTop:8}}><strong>Blocking hard requirements</strong>{decision.data.blocking_requirements.map(x=><div key={x.requirement_id} className="muted">• {x.property_key??x.requirement_id} · {x.reason_code}</div>)}</div>}{decision.data.unresolved_requirements.length>0&&<div className="notice" style={{marginTop:8}}><strong>Unresolved hard requirements</strong>{decision.data.unresolved_requirements.map(x=><div key={x.requirement_id} className="muted">• {x.property_key??x.requirement_id} · {x.reason_code}</div>)}</div>}</div>}

    {result&&<div className="card"><div className="card-pad"><div className="eyebrow">Candidate validation</div><h2><ValidationStateBadge state={result.validation_state}/></h2><p className="muted">{result.rationale}</p><div className="muted">{result.experimentally_supported_requirements.length} supported · {result.experimentally_contradicted_requirements.length} contradicted · {result.inconclusive_requirements.length} inconclusive · {result.outstanding_requirements.length} outstanding</div></div><div className="table-wrap"><table><thead><tr><th>Requirement</th><th>Reasoning</th><th>Experimental outcome</th><th>Raw → normalized evidence</th><th>Context / admissibility</th></tr></thead><tbody>{result.per_property_comparisons.map(row=><tr key={row.requirement_id}><td><strong>{row.property_key}</strong><div className="muted"><code>{row.requirement_id.slice(0,12)}…</code></div></td><td><span className="badge">{row.requirement_status}</span></td><td><span className="badge">{OUTCOME_LABELS[row.experimental_outcome]??row.experimental_outcome}</span></td><td>{row.experimental_values.length?row.experimental_values.map(v=><div key={v.measurement_id}><OriginBadge origin="experimental"/> {v.raw_value} {v.raw_unit} → <strong>{v.value} {v.unit}</strong>{v.uncertainty!=null?` ± ${v.uncertainty}`:""}</div>):<span className="muted">No admissible physical measurement</span>}</td><td>{row.experimental_values.map(v=><div key={v.measurement_id} className="muted">{v.admissibility} · {(v.admissibility_codes??[]).join(", ")||"all admission checks passed"}</div>)}</td></tr>)}</tbody></table></div></div>}

    <div className="card card-pad"><div className="eyebrow">Experiment recommendation → plan</div><h2>Close only the evidence gaps that matter</h2><div className="grid grid-2"><label className="label">Traceable candidate sample<select className="select" value={selectedSampleId} onChange={e=>setSelectedSample(e.target.value)}><option value="">— no sample —</option>{samples.data?.map(s=><option key={s.id} value={s.id}>{s.sample_code} · {s.provenance_complete?"provenance complete":"incomplete provenance"}</option>)}</select></label><label className="label">Instrument<select className="select" value={selectedInstrumentId} onChange={e=>setSelectedInstrument(e.target.value)}><option value="">— no instrument —</option>{instruments.data?.map(i=><option key={i.id} value={i.id}>{i.display_name} · {i.calibration_status}</option>)}</select></label></div><div className="muted" style={{marginTop:6}}>A plan is enabled only when the recommendation has a registered protocol and a specimen/instrument are selected. The backend still re-validates protocol property, candidate/sample ownership, calibration and protocol requirements.</div>{recommendations.data?.recommendations.length?recommendations.data.recommendations.map(r=><div className="notice" key={r.requirement_id} style={{marginTop:10}}><strong>{r.requirement_display_name}</strong><div className="muted">{r.why_it_matters}</div><div className="muted">Proposed: {r.proposed_measurement} · priority {r.priority_score.toFixed(3)} · protocol {r.suggested_protocol_key??"not registered"}</div><button className="btn btn-secondary" style={{marginTop:7}} disabled={createPlan.isPending||!r.suggested_protocol_id||!selectedSampleId||!selectedInstrumentId} onClick={()=>createPlan.mutate(r.requirement_id)}>Create pinned experiment plan</button></div>):<div className="empty">No unresolved evidence gap currently requires an experiment.</div>}{createPlan.error&&<div className="notice fail" style={{marginTop:8}}>{(createPlan.error as Error).message}</div>}</div>

    <div className="card"><div className="card-pad"><div className="eyebrow">Experiment execution</div><h2>Plan → prepare → start → complete / invalidate</h2><p className="muted">Invalid transitions are rejected server-side. Measurements recorded before completion remain provisional; invalidated-run measurements remain visible as history but stop governing decisions. A completed run closes a decision action only when this run contributes an admissible persisted measurement and the resulting requirement outcome is SUPPORTS or CONTRADICTS; inconclusive/conflicting results stay open.</p><label className="label">Invalidation reason<input className="input" value={invalidationReason} onChange={e=>setInvalidationReason(e.target.value)}/></label></div><div className="table-wrap"><table><thead><tr><th>Run</th><th>Plan</th><th>State</th><th>Context</th><th>Allowed action</th></tr></thead><tbody>{runs.data?.map(run=>{const plan=plans.data?.find(p=>p.id===run.plan_id);return <tr key={run.id}><td><strong>{run.run_code}</strong>{run.is_control&&<div className="muted">control</div>}</td><td>{plan?.display_name??"—"}</td><td><span className="badge">{run.status}</span></td><td className="muted">{Object.entries(run.conditions??{}).map(([k,v])=>`${k}=${String(v)}`).join(" · ")||"No conditions recorded"}</td><td style={{display:"flex",gap:5,flexWrap:"wrap"}}>{run.status==="planned"&&<><button className="btn btn-secondary" onClick={()=>runAction.mutate({runId:run.id,action:"ready"})}>Prepare</button><button className="btn btn-secondary" onClick={()=>runAction.mutate({runId:run.id,action:"cancel"})}>Cancel</button></>}{run.status==="ready"&&<><button className="btn" onClick={()=>runAction.mutate({runId:run.id,action:"start"})}>Start</button><button className="btn btn-secondary" onClick={()=>runAction.mutate({runId:run.id,action:"cancel"})}>Cancel</button></>}{["running","in_progress"].includes(run.status)&&<><button className="btn" onClick={()=>runAction.mutate({runId:run.id,action:"complete"})}>Complete</button><button className="btn btn-secondary" onClick={()=>runAction.mutate({runId:run.id,action:"invalidate"})}>Invalidate</button></>}{run.status==="completed"&&<button className="btn btn-secondary" onClick={()=>runAction.mutate({runId:run.id,action:"invalidate"})}>Invalidate</button>}{["invalidated","cancelled","aborted"].includes(run.status)&&<span className="muted">Terminal</span>}</td></tr>})}</tbody></table></div>{!runs.data?.length&&<div className="empty">No candidate-bound experiment plan exists yet.</div>}</div>

    <div className="card"><div className="card-pad"><div className="eyebrow">Experimental provenance</div><h2>Measurements remain inspectable even when rejected or invalidated</h2></div><div className="table-wrap"><table><thead><tr><th>Measurement</th><th>Raw</th><th>Canonical</th><th>Quality</th><th>Admission reason</th></tr></thead><tbody>{measurements.data?.map(m=><tr key={m.id}><td><code>{m.id.slice(0,12)}…</code><div className="muted">run {m.run_id.slice(0,10)}…</div></td><td>{m.numeric_value} {m.unit}</td><td>{m.canonical_value} {m.canonical_unit}</td><td><MeasurementQualityBadge quality={m.quality}/></td><td className="muted">{m.admissibility_codes.length?m.admissibility_codes.join(" · "):"All admission checks passed"}{m.quality_reasons.map((r,i)=><div key={i}>• {r}</div>)}</td></tr>)}</tbody></table></div>{!measurements.data?.length&&<div className="empty">No measurement is bound to this candidate.</div>}</div>

    {(validation.error||decision.error||recommendations.error||runAction.error)&&<div className="notice fail">{(validation.error as Error)?.message??(decision.error as Error)?.message??(recommendations.error as Error)?.message??(runAction.error as Error)?.message}</div>}
  </div>;
}
