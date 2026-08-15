"use client";
import {use, useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {api,CandidateSearchSpace,PredictionModel,PredictionModelVersion,ProjectDetail,VirtualCampaign,VirtualPolicy} from "@/lib/api";
import {VirtualEvaluationWarning} from "@/components/VirtualEvaluationWarning";
import {LabGate} from "@/components/ReadinessPanel";

function targetConditions(v:PredictionModelVersion){
  const ranges=v.applicability_domain?.target_condition_ranges??{}; const out:Record<string,unknown>={};
  for(const [key,raw] of Object.entries(ranges)){const r=raw as {min?:number;max?:number;unit?:string;required?:boolean};if(r.required&&r.min!==undefined&&r.max!==undefined)out[key]={value:(r.min+r.max)/2,unit:r.unit};}
  return out;
}
export default function VirtualLabPage({params}:{params:Promise<{id:string}>}){
  const {id}=use(params);const router=useRouter();const qc=useQueryClient();
  const project=useQuery({queryKey:["project",id],queryFn:()=>api<ProjectDetail>(`/replacement-projects/${id}`)});
  const spaces=useQuery({queryKey:["search-spaces",id],queryFn:()=>api<CandidateSearchSpace[]>(`/replacement-projects/${id}/search-spaces`)});
  const models=useQuery({queryKey:["prediction-models"],queryFn:()=>api<PredictionModel[]>(`/prediction-models`)});
  const versions=useQuery({queryKey:["all-approved-model-versions",models.data?.map(m=>m.id).join(",")],enabled:!!models.data?.length,queryFn:async()=>{
    const rows=await Promise.all((models.data??[]).map(m=>api<PredictionModelVersion[]>(`/prediction-models/${m.id}/versions`)));return rows.flat().filter(v=>!!v.approved_at&&!v.retired_at);
  }});
  const campaigns=useQuery({queryKey:["virtual-campaigns",id],queryFn:()=>api<VirtualCampaign[]>(`/replacement-projects/${id}/virtual-campaigns`)});
  const policies=useQuery({queryKey:["virtual-policies"],queryFn:()=>api<VirtualPolicy[]>(`/virtual-experiment-policies`)});
  const activeSpace=spaces.data?.find(s=>s.active)??spaces.data?.[0];
  const [name,setName]=useState("Bounded multi-objective campaign");const [policy,setPolicy]=useState("robust_pareto_v1");const [seed,setSeed]=useState(42);const [iterations,setIterations]=useState(2);const [newBudget,setNewBudget]=useState(20);const [perIteration,setPerIteration]=useState(10);const [parents,setParents]=useState(3);
  const defaultA=versions.data?.find(v=>v.target_property_key==="tensile_strength")??versions.data?.[0];const defaultB=versions.data?.find(v=>v.target_property_key==="density")??versions.data?.find(v=>v.id!==defaultA?.id);
  const [versionA,setVersionA]=useState("");const [versionB,setVersionB]=useState("");const selectedA=versions.data?.find(v=>v.id===(versionA||defaultA?.id));const selectedB=versions.data?.find(v=>v.id===(versionB||defaultB?.id));
  const [directionA,setDirectionA]=useState<"maximize"|"minimize">("maximize");const [directionB,setDirectionB]=useState<"maximize"|"minimize">("minimize");
  const create=useMutation({mutationFn:async()=>{
    if(!project.data||!activeSpace||!selectedA)throw new Error("Project, active search space, and at least one approved model are required");
    const objs=[{property_key:selectedA.target_property_key,direction:directionA,weight:1,priority:1,model_version_id:selectedA.id,evaluation_mode:"model_prediction",metadata:{conditions:targetConditions(selectedA)}}];
    if(selectedB&&selectedB.id!==selectedA.id)objs.push({property_key:selectedB.target_property_key,direction:directionB,weight:1,priority:2,model_version_id:selectedB.id,evaluation_mode:"model_prediction",metadata:{conditions:targetConditions(selectedB)}});
    const byProperty=new Map([selectedA,selectedB].filter(Boolean).map(v=>[(v as PredictionModelVersion).target_property_key,v as PredictionModelVersion]));
    const constraint_policies=project.data.constraints.filter(c=>c.hard_or_soft==="hard"&&byProperty.has(c.property_key)).map(c=>{const v=byProperty.get(c.property_key)!;return {constraint_id:c.id,model_version_id:v.id,allowed_value_origin:"known_evidence_then_prediction",unknown_handling:"retain_uncertain",condition_mapping:targetConditions(v),enabled:true,metadata:{source:"virtual_lab_ui"}}});
    return api<VirtualCampaign>(`/replacement-projects/${id}/virtual-campaigns`,{method:"POST",body:JSON.stringify({name,description:"Bounded model-based virtual evaluation campaign.",search_space_id:activeSpace.id,policy_key:policy,random_seed:seed,max_iterations:iterations,max_total_new_candidates:newBudget,max_candidates_per_iteration:perIteration,max_parents_per_iteration:parents,created_by:project.data.created_by,objectives:objs,constraint_policies,initial_candidate_ids:[],include_known_candidates:true,exploration_enabled:true,mutation_types:["component_amount","component_substitution","process_parameter"],metadata:{source:"virtual_lab_ui"}})});
  },onSuccess:async c=>{await qc.invalidateQueries({queryKey:["virtual-campaigns",id]});router.push(`/virtual-campaigns/${c.id}`);}});
  if(project.isLoading||spaces.isLoading||models.isLoading)return <div className="empty">Loading Virtual Experiment Lab…</div>;
  if(project.error||!project.data)return <div className="empty">Virtual Experiment Lab unavailable: {(project.error as Error)?.message}</div>;
  return <div className="grid">
    <div className="topline"><div><div className="eyebrow">Virtual Experiment Lab · Phase 5</div><h1>{project.data.name}</h1><div className="muted">Bounded uncertainty-aware multi-objective exploration over the Phase-3 search space.</div></div><div style={{display:"flex",gap:8}}><Link className="btn btn-secondary" href={`/projects/${id}/prediction-lab`}>Prediction Lab</Link><Link className="btn btn-secondary" href={`/projects/${id}`}>Project</Link></div></div>
    <LabGate projectId={id} labKey="virtual_lab"/>
    <VirtualEvaluationWarning/>
    <div className="card card-pad"><div className="eyebrow">Campaign Builder</div><h2>Pin scientific semantics before optimization</h2><p className="muted">Campaigns pin the replacement specification, search-space checksum, model versions, policy, seed, and bounded budgets. Completed campaigns are not edited in place.</p>
      <div className="grid grid-2">
        <label className="label">Campaign name<input className="input" value={name} onChange={e=>setName(e.target.value)}/></label>
        <label className="label">Policy<select className="select" value={policy} onChange={e=>setPolicy(e.target.value)}>{policies.data?.map(p=><option key={p.key} value={p.key}>{p.key} · v{p.version}</option>)}</select></label>
        <label className="label">Objective 1 model<select className="select" value={selectedA?.id??""} onChange={e=>setVersionA(e.target.value)}>{versions.data?.map(v=><option key={v.id} value={v.id}>{v.target_property_key} · v{v.version}</option>)}</select></label>
        <label className="label">Objective 1 direction<select className="select" value={directionA} onChange={e=>setDirectionA(e.target.value as "maximize"|"minimize")}><option value="maximize">maximize</option><option value="minimize">minimize</option></select></label>
        <label className="label">Objective 2 model<select className="select" value={selectedB?.id??""} onChange={e=>setVersionB(e.target.value)}><option value="">None</option>{versions.data?.filter(v=>v.id!==selectedA?.id).map(v=><option key={v.id} value={v.id}>{v.target_property_key} · v{v.version}</option>)}</select></label>
        <label className="label">Objective 2 direction<select className="select" value={directionB} onChange={e=>setDirectionB(e.target.value as "maximize"|"minimize")}><option value="minimize">minimize</option><option value="maximize">maximize</option></select></label>
        <label className="label">Random seed<input className="input" type="number" value={seed} onChange={e=>setSeed(Number(e.target.value))}/></label>
        <label className="label">Max iterations (1–5)<input className="input" type="number" min={1} max={5} value={iterations} onChange={e=>setIterations(Number(e.target.value))}/></label>
        <label className="label">New-candidate campaign budget<input className="input" type="number" min={0} max={500} value={newBudget} onChange={e=>setNewBudget(Number(e.target.value))}/></label>
        <label className="label">Children / iteration<input className="input" type="number" min={1} max={200} value={perIteration} onChange={e=>setPerIteration(Number(e.target.value))}/></label>
        <label className="label">Parents / iteration<input className="input" type="number" min={0} max={100} value={parents} onChange={e=>setParents(Number(e.target.value))}/></label>
        <div className="notice"><strong>Search space</strong><div>{activeSpace?`v${activeSpace.version} · ${activeSpace.material_family}`:"No active search space"}</div><div className="muted"><code>{activeSpace?.checksum??"—"}</code></div></div>
      </div>
      <div style={{marginTop:14}}><button className="btn" disabled={create.isPending||!selectedA||!activeSpace} onClick={()=>create.mutate()}>Create draft campaign</button>{!activeSpace&&<span className="muted" style={{marginLeft:10}}>Needs an active search space — see the panel above.</span>}{activeSpace&&!selectedA&&<span className="muted" style={{marginLeft:10}}>Needs at least one approved prediction model.</span>}{create.error&&<div className="notice fail" style={{marginTop:10}}>{(create.error as Error).message}</div>}</div>
    </div>
    <div className="card"><div className="card-pad"><div className="eyebrow">Campaign History</div><h2>Auditable virtual campaigns</h2></div><div className="table-wrap"><table><thead><tr><th>Campaign</th><th>Policy</th><th>Status</th><th>Budgets</th><th>Stop reason</th><th>Result checksum</th></tr></thead><tbody>{campaigns.data?.map(c=><tr key={c.id}><td><Link href={`/virtual-campaigns/${c.id}`}><strong>{c.name}</strong></Link><div className="muted">seed {c.random_seed}</div></td><td>{c.policy_key} · v{c.policy_version}</td><td><span className="badge">{c.status}</span></td><td>{c.max_iterations} iterations · {c.max_total_new_candidates} new</td><td>{c.stop_reason??"—"}</td><td><code>{c.result_checksum?.slice(0,14)??"—"}…</code></td></tr>)}</tbody></table></div></div>
    <div className="card card-pad"><div className="eyebrow">Policy semantics</div><div className="grid grid-3">{policies.data?.map(p=><div className="notice" key={p.key}><strong>{p.key}</strong><div className="muted">{p.uncertainty_semantics}</div><div className="muted">UNKNOWN: {p.unknown_handling}</div></div>)}</div></div>
  </div>;
}
