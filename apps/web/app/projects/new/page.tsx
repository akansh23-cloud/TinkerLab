"use client";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, MaterialSummary } from "@/lib/api";
import { useRouter } from "next/navigation";

const REASONS = ["cost","regulation","supply_risk","sustainability","performance","weight","toxicity","availability","custom"];
type ConstraintDraft = {property_key:string;comparator:string;target_value:number;target_unit:string;hard_or_soft:"hard"|"soft";weight:number;severity:number};
type ObjectiveDraft = {property_key:string;direction:"minimize"|"maximize"|"target";weight:number;priority:number};
const HARD_DEFAULTS: ConstraintDraft[] = [
  {property_key:"density", comparator:"<=", target_value:1.35, target_unit:"g/cm^3", hard_or_soft:"hard", weight:1, severity:5},
  {property_key:"tensile_strength", comparator:">=", target_value:70, target_unit:"MPa", hard_or_soft:"hard", weight:1, severity:5},
];
const SOFT_DEFAULTS: ConstraintDraft[] = [
  {property_key:"carbon_footprint", comparator:"<=", target_value:3, target_unit:"kgCO2e/kg", hard_or_soft:"soft", weight:.8, severity:3},
];
const OBJECTIVE_DEFAULTS: ObjectiveDraft[] = [
  {property_key:"cost_per_mass", direction:"minimize", weight:.8, priority:1},
  {property_key:"density", direction:"minimize", weight:.6, priority:2},
];

export default function NewProjectPage(){
  const router = useRouter();
  const [step,setStep]=useState(1);
  const [name,setName]=useState("New material replacement study");
  const [description,setDescription]=useState("Define a transparent replacement specification before any discovery workflow begins.");
  const [baseline,setBaseline]=useState("");
  const [reasons,setReasons]=useState<string[]>(["cost"]);
  const [hard,setHard]=useState<ConstraintDraft[]>(HARD_DEFAULTS);
  const [soft,setSoft]=useState<ConstraintDraft[]>(SOFT_DEFAULTS);
  const [objectives,setObjectives]=useState<ObjectiveDraft[]>(OBJECTIVE_DEFAULTS);
  const {data:materials}=useQuery({queryKey:["materials"],queryFn:()=>api<MaterialSummary[]>("/materials")});
  const {data:ctx}=useQuery({queryKey:["demo-context"],queryFn:()=>api<{organisation_id:string;user_id:string}>("/demo-context")});
  useEffect(()=>{ if(!baseline && materials?.[0]) setBaseline(materials[0].id); },[materials,baseline]);

  const preview = useMemo(()=>({
    version:"1.0", baseline_material:baseline, reasons:[...reasons].sort(),
    hard_constraints:hard.map(({property_key,comparator,target_value,target_unit})=>({property:property_key,operator:comparator,value:target_value,unit:target_unit})),
    soft_constraints:soft.map(({property_key,comparator,target_value,target_unit})=>({property:property_key,operator:comparator,value:target_value,unit:target_unit})),
    objectives:objectives.map(({property_key,direction,weight})=>({property:property_key,direction,weight})),
  }),[baseline,reasons,hard,soft,objectives]);

  const create = useMutation({mutationFn:async()=>{
    if(!ctx) throw new Error("Demo context unavailable");
    const project = await api<{id:string}>("/replacement-projects",{method:"POST",body:JSON.stringify({organisation_id:ctx.organisation_id,created_by:ctx.user_id,name,description,baseline_material_id:baseline,replacement_reasons:reasons,status:"draft"})});
    for(const c of [...hard,...soft]) await api(`/replacement-projects/${project.id}/constraints`,{method:"POST",body:JSON.stringify(c)});
    for(const o of objectives) await api(`/replacement-projects/${project.id}/objectives`,{method:"POST",body:JSON.stringify(o)});
    return project;
  },onSuccess:p=>router.push(`/projects/${p.id}`)});

  function updateRow<T extends object>(rows:T[],setRows:(x:T[])=>void,index:number,key:string,value:string|number|boolean){setRows(rows.map((r,i)=>i===index?{...r,[key]:value}:r));}
  const constraintEditor=(rows:ConstraintDraft[],setRows:(x:ConstraintDraft[])=>void)=> <div className="grid">
    {rows.map((c,i)=><div key={i} className="card card-pad grid grid-3">
      <label className="label">Property<input className="input" value={c.property_key} onChange={e=>updateRow(rows,setRows,i,"property_key",e.target.value)}/></label>
      <label className="label">Comparator<select className="select" value={c.comparator} onChange={e=>updateRow(rows,setRows,i,"comparator",e.target.value)}>{["<","<=","=",">=",">","between"].map(x=><option key={x}>{x}</option>)}</select></label>
      <label className="label">Target<div style={{display:"flex",gap:6}}><input className="input" type="number" value={c.target_value} onChange={e=>updateRow(rows,setRows,i,"target_value",Number(e.target.value))}/><input className="input" value={c.target_unit} onChange={e=>updateRow(rows,setRows,i,"target_unit",e.target.value)}/></div></label>
    </div>)}
    <button className="btn btn-secondary" onClick={()=>setRows([...rows,{property_key:"density",comparator:"<=",target_value:0,target_unit:"kg/m^3",hard_or_soft:rows===hard?"hard":"soft",weight:1,severity:3}])}>Add constraint</button>
  </div>;

  return <>
    <div className="topline"><div><div className="eyebrow">New replacement study</div><h1>Compile the scientific problem first</h1><div className="muted">Eight explicit steps produce a typed replacement specification. No material is generated in Phase 1.</div></div></div>
    <div className="wizard-steps">{Array.from({length:8},(_,i)=><div key={i} className={`wizard-step ${i<step?"active":""}`}/>)}</div>
    <div className="card card-pad" style={{minHeight:390}}>
      {step===1&&<div className="grid"><h2>1. Define project</h2><label className="label">Project name<input className="input" value={name} onChange={e=>setName(e.target.value)}/></label><label className="label">Description<textarea className="textarea" rows={5} value={description} onChange={e=>setDescription(e.target.value)}/></label></div>}
      {step===2&&<div className="grid"><h2>2. Select baseline material</h2><label className="label">Existing material<select className="select" value={baseline} onChange={e=>setBaseline(e.target.value)}>{materials?.map(m=><option key={m.id} value={m.id}>{m.display_name} · {m.material_family}</option>)}</select></label><div className="notice">The baseline defines the current state. Candidate values are never copied from the baseline when evidence is missing.</div></div>}
      {step===3&&<div className="grid"><h2>3. Why replace it?</h2>{REASONS.map(r=><label key={r} className="checkbox-row"><input type="checkbox" checked={reasons.includes(r)} onChange={e=>setReasons(e.target.checked?[...reasons,r]:reasons.filter(x=>x!==r))}/><span><strong>{r.replaceAll("_"," ")}</strong></span></label>)}</div>}
      {step===4&&<div className="grid"><h2>4. Hard requirements</h2><div className="muted">A hard constraint can eliminate a candidate. Missing evidence stays UNKNOWN.</div>{constraintEditor(hard,setHard)}</div>}
      {step===5&&<div className="grid"><h2>5. Soft requirements</h2><div className="muted">Soft constraints describe preference without pretending to be absolute qualification gates.</div>{constraintEditor(soft,setSoft)}</div>}
      {step===6&&<div className="grid"><h2>6. Optimisation objectives</h2>{objectives.map((o,i)=><div key={i} className="card card-pad grid grid-3"><label className="label">Property<input className="input" value={o.property_key} onChange={e=>updateRow(objectives,setObjectives,i,"property_key",e.target.value)}/></label><label className="label">Direction<select className="select" value={o.direction} onChange={e=>updateRow(objectives,setObjectives,i,"direction",e.target.value)}><option value="minimize">minimize</option><option value="maximize">maximize</option><option value="target">target</option></select></label><label className="label">Weight<input className="input" type="number" step="0.1" value={o.weight} onChange={e=>updateRow(objectives,setObjectives,i,"weight",Number(e.target.value))}/></label></div>)}</div>}
      {step===7&&<div className="grid"><h2>7. Review specification</h2><div className="notice">This is a client preview. The backend recompiles and hashes the authoritative semantic specification after creation.</div><pre className="json">{JSON.stringify(preview,null,2)}</pre></div>}
      {step===8&&<div className="grid"><h2>8. Create project</h2><div className="grid grid-3"><div className="card stat"><span className="kicker">Hard constraints</span><strong>{hard.length}</strong></div><div className="card stat"><span className="kicker">Soft constraints</span><strong>{soft.length}</strong></div><div className="card stat"><span className="kicker">Objectives</span><strong>{objectives.length}</strong></div></div><div className="notice">Creation persists the project, then persists each typed constraint and objective through validated API contracts.</div>{create.error&&<div className="notice">{(create.error as Error).message}</div>}</div>}
    </div>
    <div style={{display:"flex",justifyContent:"space-between",marginTop:16}}><button className="btn btn-secondary" disabled={step===1} onClick={()=>setStep(Math.max(1,step-1))}>Back</button>{step<8?<button className="btn" onClick={()=>setStep(Math.min(8,step+1))}>Continue</button>:<button className="btn" disabled={create.isPending||!ctx||!baseline||reasons.length===0} onClick={()=>create.mutate()}>{create.isPending?"Creating…":"Create study"}</button>}</div>
  </>;
}
