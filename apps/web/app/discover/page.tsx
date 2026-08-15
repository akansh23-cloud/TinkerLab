"use client";

import {FormEvent, useMemo, useState} from "react";
import {api} from "@/lib/api";

type Operator = ">=" | "<=" | ">" | "<" | "==";
type DiscoveryConstraint = {property_key:string; operator:Operator; threshold:number; tolerance?:number};
type RequirementResult = {
  property_key:string; operator:string; threshold:number; observed_value:number|null;
  status:"PASS"|"FAIL"|"UNKNOWN"; reason:string; evidence_origin:string;
};
type DiscoveryCandidate = {
  rank:number; material_id:string; formula_pretty:string; formula_reduced:string; chemsys:string;
  is_stable:boolean|null; theoretical:boolean|null; energy_above_hull_ev_atom:number|null;
  n_elements:number|null; n_sites:number|null; pass_count:number; fail_count:number; unknown_count:number;
  evidence_coverage:number; screening_state:string; observations:Record<string,number|null>;
  requirements:RequirementResult[]; origins:Array<Record<string,unknown>>;
};
type DiscoveryResponse = {
  provider:string; provider_version:string; source_data_kind:string; preview_only:boolean; persisted:boolean;
  ranking_policy:string; requested_constraints:DiscoveryConstraint[]; requested_filters:Record<string,unknown>;
  candidate_count:number; candidates:DiscoveryCandidate[];
};

type FormState = {
  elements:string; excludeElements:string; chemsys:string; formula:string; stableOnly:boolean; limit:number;
  minBandGap:string; maxDensity:string; maxHull:string; minBulk:string; minShear:string;
};

const initial:FormState={
  elements:"",excludeElements:"Pb,Cd,Hg",chemsys:"",formula:"",stableOnly:true,limit:25,
  minBandGap:"",maxDensity:"",maxHull:"0.05",minBulk:"",minShear:"",
};

function numberConstraint(value:string, property_key:string, operator:Operator):DiscoveryConstraint|null{
  if(value.trim()==="") return null;
  const threshold=Number(value);
  return Number.isFinite(threshold)?{property_key,operator,threshold}:null;
}
function splitElements(value:string){return value.split(/[,\s]+/).map(v=>v.trim()).filter(Boolean)}
function pct(value:number){return `${Math.round(Math.max(0,Math.min(1,value))*100)}%`}
function observed(candidate:DiscoveryCandidate,key:string){const value=candidate.observations?.[key];return typeof value==="number"?value:null}
function formatValue(value:number|null,unit:string){return value===null?"—":`${Number(value.toFixed(4))} ${unit}`}

export default function MaterialsDiscoveryPage(){
  const [form,setForm]=useState<FormState>(initial);
  const [result,setResult]=useState<DiscoveryResponse|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");

  const constraints=useMemo(()=>[
    numberConstraint(form.minBandGap,"band_gap_ev",">="),
    numberConstraint(form.maxDensity,"density_g_cm3","<="),
    numberConstraint(form.maxHull,"energy_above_hull_ev_atom","<="),
    numberConstraint(form.minBulk,"bulk_modulus_gpa",">="),
    numberConstraint(form.minShear,"shear_modulus_gpa",">="),
  ].filter((v):v is DiscoveryConstraint=>v!==null),[form]);

  async function discover(event:FormEvent){
    event.preventDefault();setLoading(true);setError("");setResult(null);
    try{
      const payload={
        constraints,
        elements:splitElements(form.elements),
        exclude_elements:splitElements(form.excludeElements),
        chemsys:form.chemsys.trim()||null,
        formula:form.formula.trim()||null,
        is_stable:form.stableOnly?true:null,
        limit:Math.max(1,Math.min(100,form.limit)),
      };
      const response=await api<DiscoveryResponse>("/external-data/materials-project/discover",{method:"POST",body:JSON.stringify(payload)});
      setResult(response);
    }catch(e){setError(e instanceof Error?e.message:"Materials Project discovery failed.")}
    finally{setLoading(false)}
  }

  return <div className="workspace-page">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Materials Project · read-only discovery</span><h1>Screen real computed materials before importing anything.</h1><p>Translate engineering constraints into a Materials Project search, then inspect PASS / FAIL / UNKNOWN evidence and provenance. Results remain a non-persistent screening preview.</p></div>
    </div>

    <section className="command-panel" style={{marginBottom:20}}>
      <div className="panel-title-row"><div><span className="panel-kicker">Search definition</span><h2>Constraint-aware candidate discovery</h2></div><span className="count-chip">{constraints.length} constraints</span></div>
      <form onSubmit={discover}>
        <div className="form-grid" style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(210px,1fr))",gap:14}}>
          <label><small>Required elements</small><input value={form.elements} onChange={e=>setForm({...form,elements:e.target.value})} placeholder="Si, O, Al"/></label>
          <label><small>Excluded elements</small><input value={form.excludeElements} onChange={e=>setForm({...form,excludeElements:e.target.value})} placeholder="Pb, Cd, Hg"/></label>
          <label><small>Chemical system</small><input value={form.chemsys} onChange={e=>setForm({...form,chemsys:e.target.value})} placeholder="Si-O"/></label>
          <label><small>Formula</small><input value={form.formula} onChange={e=>setForm({...form,formula:e.target.value})} placeholder="SiO2"/></label>
          <label><small>Minimum band gap (eV)</small><input type="number" step="any" value={form.minBandGap} onChange={e=>setForm({...form,minBandGap:e.target.value})} placeholder="2.5"/></label>
          <label><small>Maximum density (g/cm³)</small><input type="number" step="any" value={form.maxDensity} onChange={e=>setForm({...form,maxDensity:e.target.value})} placeholder="5"/></label>
          <label><small>Maximum energy above hull (eV/atom)</small><input type="number" step="any" value={form.maxHull} onChange={e=>setForm({...form,maxHull:e.target.value})}/></label>
          <label><small>Minimum bulk modulus (GPa)</small><input type="number" step="any" value={form.minBulk} onChange={e=>setForm({...form,minBulk:e.target.value})} placeholder="100"/></label>
          <label><small>Minimum shear modulus (GPa)</small><input type="number" step="any" value={form.minShear} onChange={e=>setForm({...form,minShear:e.target.value})} placeholder="50"/></label>
          <label><small>Maximum candidates</small><input type="number" min={1} max={100} value={form.limit} onChange={e=>setForm({...form,limit:Number(e.target.value)||25})}/></label>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:14,marginTop:18,flexWrap:"wrap"}}>
          <label style={{display:"flex",alignItems:"center",gap:8}}><input type="checkbox" checked={form.stableOnly} onChange={e=>setForm({...form,stableOnly:e.target.checked})}/><span>Stable materials only</span></label>
          <button className="btn" disabled={loading||constraints.length===0} type="submit">{loading?"Searching Materials Project…":"Discover candidates"}</button>
          <button className="btn btn-secondary" type="button" onClick={()=>{setForm(initial);setResult(null);setError("")}}>Reset</button>
        </div>
      </form>
      <p className="muted" style={{marginTop:14}}>Scientific boundary: Materials Project values are treated as <strong>computed database evidence</strong>, not experimental measurements. This preview does not create materials, evidence, or replacement decisions in TinkerLab.</p>
      {constraints.length===0&&<div className="panel-empty" style={{marginTop:12}}>Add at least one numerical screening constraint before searching.</div>}
      {error&&<div className="panel-empty" style={{marginTop:12}}><strong>Discovery unavailable.</strong><p>{error}</p></div>}
    </section>

    {result&&<>
      <section className="decision-outcome-kpis" style={{marginBottom:20}}>
        <article className="neutral"><small>Returned</small><strong>{result.candidate_count}</strong><span>External candidates</span></article>
        <article className="advance"><small>Zero failures</small><strong>{result.candidates.filter(c=>c.fail_count===0).length}</strong><span>Still require qualification</span></article>
        <article className="hold"><small>Unresolved</small><strong>{result.candidates.filter(c=>c.unknown_count>0).length}</strong><span>Missing screening evidence</span></article>
        <article className="reject"><small>Screening failures</small><strong>{result.candidates.filter(c=>c.fail_count>0).length}</strong><span>Constraint violations</span></article>
      </section>

      <section className="command-panel" style={{marginBottom:20}}>
        <div className="panel-title-row"><div><span className="panel-kicker">Ranking policy</span><h2>Transparent screening order</h2></div><span className="count-chip">{result.provider}</span></div>
        <p>{result.ranking_policy}</p><p className="muted">Provider version: {result.provider_version} · Source kind: {result.source_data_kind} · Persisted: {String(result.persisted)} · Preview only: {String(result.preview_only)}</p>
      </section>

      <section style={{display:"grid",gap:16}}>
        {result.candidates.map(candidate=><article className="command-panel" key={candidate.material_id}>
          <div className="panel-title-row"><div><span className="panel-kicker">#{candidate.rank} · {candidate.material_id}</span><h2>{candidate.formula_pretty||candidate.formula_reduced}</h2><p className="muted">{candidate.chemsys} · {candidate.is_stable===true?"stable":candidate.is_stable===false?"metastable/unstable":"stability unknown"} · {candidate.theoretical===true?"theoretical entry":candidate.theoretical===false?"non-theoretical entry":"theoretical flag unknown"}</p></div><span className={`count-chip ${candidate.fail_count>0?"reject":candidate.unknown_count>0?"hold":"advance"}`}>{candidate.screening_state}</span></div>
          <div style={{display:"flex",gap:18,flexWrap:"wrap",margin:"12px 0"}}><span><strong>{candidate.pass_count}</strong> PASS</span><span><strong>{candidate.fail_count}</strong> FAIL</span><span><strong>{candidate.unknown_count}</strong> UNKNOWN</span><span><strong>{pct(candidate.evidence_coverage)}</strong> evidence coverage</span></div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10,marginBottom:14}}>
            <div><small>Band gap</small><div>{formatValue(observed(candidate,"band_gap_ev"),"eV")}</div></div>
            <div><small>Density</small><div>{formatValue(observed(candidate,"density_g_cm3"),"g/cm³")}</div></div>
            <div><small>Energy above hull</small><div>{formatValue(candidate.energy_above_hull_ev_atom,"eV/atom")}</div></div>
            <div><small>Bulk modulus</small><div>{formatValue(observed(candidate,"bulk_modulus_gpa"),"GPa")}</div></div>
            <div><small>Shear modulus</small><div>{formatValue(observed(candidate,"shear_modulus_gpa"),"GPa")}</div></div>
          </div>
          <div className="requirement-mini-table">
            <div><span>Requirement</span><span>Evidence result</span></div>
            {candidate.requirements.map((r,i)=><div key={`${candidate.material_id}-${r.property_key}-${i}`}><span>{r.property_key} {r.operator} {r.threshold}{r.observed_value!==null?` · observed ${Number(r.observed_value.toFixed(4))}`:" · no value"}</span><b className={`cell-state ${r.status==="PASS"?"pass":r.status==="FAIL"?"fail":"unknown"}`} title={r.reason}>{r.status}</b></div>)}
          </div>
          <p className="muted" style={{marginTop:12}}>Provenance references available: {candidate.origins?.length??0}. A zero-failure screening result is not an acceptance decision; qualification, applicability, uncertainty and experimental validation remain separate stages.</p>
        </article>)}
        {result.candidates.length===0&&<div className="command-panel panel-empty">No candidates matched the current external search. Relax a screening constraint or broaden the chemistry filter.</div>}
      </section>
    </>}
  </div>;
}
