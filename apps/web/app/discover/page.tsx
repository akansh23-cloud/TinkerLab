"use client";

import {FormEvent, useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {api, type ProjectSummary} from "@/lib/api";

type PropertyKey="band_gap"|"density"|"energy_above_hull"|"formation_energy_per_atom"|"bulk_modulus"|"shear_modulus"|"magnetic_moment";
type ScreeningConstraint={property:PropertyKey;minimum?:number;maximum?:number};
type Observation={property_key:string;numeric_value?:number|null;unit?:string|null;origin?:string|null;computed?:boolean};
type Evaluation={property:string;minimum:number|null;maximum:number|null;status:"pass"|"fail"|"unknown";value:number|null;unit:string|null;origin:string|null;computed:boolean|null};
type PreferenceEvaluation=Evaluation&{constraint_id?:string|null;weight:number;severity:number;description?:string|null};
type PreferenceSummary={pass:number;fail:number;unknown:number;total_weight:number;pass_weight:number;fail_weight:number;unknown_weight:number;evidence_coverage:number;known_weight_satisfaction:number|null};
type Candidate={rank:number;material_id:string;display_name:string|null;chemical_formula:string|null;elements:string[];is_stable:boolean|null;is_theoretical:boolean|null;crystal_system:string|null;space_group_symbol:string|null;constraint_summary:{pass:number;fail:number;unknown:number;evidence_coverage:number};constraint_evaluations:Evaluation[];preference_summary?:PreferenceSummary;preference_evaluations?:PreferenceEvaluation[];observations:Observation[];materials_project_origins:Array<Record<string,unknown>>;last_updated:string|null};
type TranslatedMissionConstraint={property:string;minimum:number|null;maximum:number|null;unit:string;source_constraint_ids:string[]};
type RankingPreference={constraint_id:string;property:string;minimum:number|null;maximum:number|null;unit:string;weight:number;severity:number;description?:string|null};
type UnsupportedMissionConstraint={constraint_id:string;property_key:string;comparator:string;target_value:number|null;target_value_upper:number|null;target_unit:string|null;hard_or_soft:string;weight?:number;severity?:number;reason:string;detail:string|null};
type MissionContext={project_id:string;project_name:string;baseline_material_id:string;baseline_material_name:string|null;hard_constraint_count:number;hard_constraints_represented:number;hard_constraint_coverage:number;soft_constraint_count?:number;soft_preferences_represented?:number;soft_preference_coverage?:number;translated_constraints:TranslatedMissionConstraint[];ranking_preferences?:RankingPreference[];unsupported_constraints:UnsupportedMissionConstraint[];search_semantics:string};
type DiscoveryResponse={preview_only:boolean;persisted:boolean;source:string;source_data_kind:string;warning:string;ranking_policy:{type:string;order:string[];soft_weight_semantics?:string};provider_version:string|null;records_screened:number;candidates_returned:number;candidates:Candidate[];mission_context?:MissionContext};
type AdoptResponse={project_id:string;candidate_id:string;material_id:string;source_material_id:string;attached:boolean;ingestion_status:string;dataset_snapshot_id:string|null;source_record_id:string|null;evidence_id:string|null;observations_written:number;source_data_kind:string;candidate_status:string;warning:string};
type FormState={elements:string;excludeElements:string;chemsys:string;formula:string;stableOnly:boolean;limit:number;minBandGap:string;maxDensity:string;maxHull:string;minBulk:string;minShear:string};

const initial:FormState={elements:"",excludeElements:"Pb,Cd,Hg",chemsys:"",formula:"",stableOnly:true,limit:25,minBandGap:"",maxDensity:"",maxHull:"0.05",minBulk:"",minShear:""};
const compareProperties:[string,string,string][]=[
  ["band_gap","Band gap","eV"],["density","Density","g/cm³"],["energy_above_hull","Energy above hull","eV/atom"],["formation_energy_per_atom","Formation energy","eV/atom"],["bulk_modulus","Bulk modulus","GPa"],["shear_modulus","Shear modulus","GPa"],["magnetic_moment","Magnetic moment",""]
];
function split(value:string){return value.split(/[,\s]+/).map(v=>v.trim()).filter(Boolean)}
function optionalList(value:string){const rows=split(value);return rows.length?rows:null}
function bound(value:string,property:PropertyKey,kind:"minimum"|"maximum"):ScreeningConstraint|null{if(!value.trim())return null;const n=Number(value);return Number.isFinite(n)?{property,[kind]:n}:null}
function pct(value:number){return `${Math.round(Math.max(0,Math.min(1,value))*100)}%`}
function observation(c:Candidate,key:string){return c.observations.find(o=>o.property_key===key)?.numeric_value??null}
function fmt(value:number|null|undefined,unit:string){return typeof value==="number"?`${Number(value.toFixed(4))}${unit?` ${unit}`:""}`:"—"}
function readableReason(value:string){return value.replaceAll("_"," ")}
function candidateName(c:Candidate){return c.display_name||c.chemical_formula||c.material_id}
function screeningState(c:Candidate){return c.constraint_summary.fail?"FAIL":c.constraint_summary.unknown?"UNRESOLVED":"PASS"}
function rankingExplanation(candidate:Candidate,previous?:Candidate){
  if(!previous)return "Highest-ranked candidate under the deterministic mission policy. Hard-gate state is evaluated before soft preference.";
  const hard=candidate.constraint_summary,prevHard=previous.constraint_summary;
  if(hard.fail!==prevHard.fail)return `Hard-gate failures differ (${hard.fail} versus ${prevHard.fail} above); fewer failures always win.`;
  if(hard.unknown!==prevHard.unknown)return `Hard failures tie; unresolved hard evidence differs (${hard.unknown} versus ${prevHard.unknown} above).`;
  const soft=candidate.preference_summary,prevSoft=previous.preference_summary;
  if(soft&&prevSoft){
    if(soft.fail_weight!==prevSoft.fail_weight)return `Hard state ties; weighted soft failure is ${soft.fail_weight} versus ${prevSoft.fail_weight} above.`;
    if(soft.unknown_weight!==prevSoft.unknown_weight)return `Weighted soft failure ties; unresolved soft weight is ${soft.unknown_weight} versus ${prevSoft.unknown_weight} above.`;
    if(soft.pass_weight!==prevSoft.pass_weight)return `Earlier stages tie; satisfied soft weight is ${soft.pass_weight} versus ${prevSoft.pass_weight} above.`;
  }
  if(hard.evidence_coverage!==prevHard.evidence_coverage)return `Earlier stages tie; hard evidence coverage (${pct(hard.evidence_coverage)}) is the next discriminator.`;
  return "Earlier ranking stages tie; stability, theoretical-entry status, energy above hull, then material ID provide deterministic tie-breaks.";
}

export default function MaterialsDiscoveryPage(){
  const [form,setForm]=useState(initial);
  const [result,setResult]=useState<DiscoveryResponse|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [projects,setProjects]=useState<ProjectSummary[]>([]);
  const [projectId,setProjectId]=useState("");
  const [adopting,setAdopting]=useState("");
  const [adopted,setAdopted]=useState<Record<string,AdoptResponse>>({});
  const [adoptError,setAdoptError]=useState("");
  const [compareIds,setCompareIds]=useState<string[]>([]);

  useEffect(()=>{api<ProjectSummary[]>("/replacement-projects").then(rows=>{setProjects(rows);if(rows[0])setProjectId(rows[0].id)}).catch(()=>setProjects([]))},[]);
  const constraints=useMemo(()=>[
    bound(form.minBandGap,"band_gap","minimum"),bound(form.maxDensity,"density","maximum"),bound(form.maxHull,"energy_above_hull","maximum"),bound(form.minBulk,"bulk_modulus","minimum"),bound(form.minShear,"shear_modulus","minimum")
  ].filter((v):v is ScreeningConstraint=>v!==null),[form]);
  const selectedProject=projects.find(p=>p.id===projectId);
  const compared=useMemo(()=>result?.candidates.filter(c=>compareIds.includes(c.material_id))??[],[result,compareIds]);
  function commonPayload(){const max=Math.max(1,Math.min(100,form.limit));return {formula:form.formula.trim()||null,chemsys:form.chemsys.trim()||null,elements:optionalList(form.elements),exclude_elements:optionalList(form.excludeElements),is_stable:form.stableOnly?true:null,theoretical:null,stable_preferred:true,max_candidates:max,search_pool:Math.max(max,Math.min(500,max*4))}}
  function resetResults(){setResult(null);setAdopted({});setCompareIds([])}
  function toggleCompare(id:string){setCompareIds(current=>current.includes(id)?current.filter(v=>v!==id):current.length<5?[...current,id]:current)}

  async function discover(e:FormEvent){e.preventDefault();setLoading(true);setError("");resetResults();try{setResult(await api<DiscoveryResponse>("/external-data/materials-project/discover",{method:"POST",body:JSON.stringify({...commonPayload(),constraints})}))}catch(e){setError(e instanceof Error?e.message:"Materials Project discovery failed.")}finally{setLoading(false)}}
  async function discoverMission(){if(!projectId)return;setLoading(true);setError("");resetResults();try{setResult(await api<DiscoveryResponse>("/external-data/materials-project/discover-mission",{method:"POST",body:JSON.stringify({...commonPayload(),project_id:projectId})}))}catch(e){setError(e instanceof Error?e.message:"Mission-driven discovery failed.")}finally{setLoading(false)}}
  async function adopt(candidate:Candidate){if(!projectId)return;setAdopting(candidate.material_id);setAdoptError("");try{const response=await api<AdoptResponse>("/external-data/materials-project/adopt",{method:"POST",body:JSON.stringify({material_id:candidate.material_id,project_id:projectId})});setAdopted(v=>({...v,[candidate.material_id]:response}))}catch(e){setAdoptError(e instanceof Error?e.message:"Candidate adoption failed.")}finally{setAdopting("")}}

  return <div className="workspace-page">
    <div className="workspace-hero compact"><div><span className="workspace-kicker">Materials Project · evidence-aware discovery</span><h1>Discover, compare, then qualify replacement candidates.</h1><p>Screen against mission gates, keep uncertainty explicit, compare 2–5 candidates side by side, and only then admit reviewed materials into the qualification workflow.</p></div></div>

    <section className="command-panel" style={{marginBottom:20}}>
      <div className="panel-title-row"><div><span className="panel-kicker">Mission-driven discovery</span><h2>Screen from approved replacement requirements</h2></div><span className="count-chip">read-only preview</span></div>
      {projects.length?<><div style={{display:"flex",gap:12,alignItems:"end",flexWrap:"wrap"}}><label style={{minWidth:320}}><small>Replacement mission</small><select value={projectId} onChange={e=>setProjectId(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button className="btn" type="button" disabled={!projectId||loading} onClick={discoverMission}>{loading?"Screening mission…":"Discover from mission"}</button>{projectId&&<Link className="btn btn-secondary" href={`/projects/${projectId}/replacement`}>Open mission</Link>}</div><p className="muted" style={{marginTop:12}}>Only requirements that can be represented without changing their scientific meaning become upstream filters. Unsupported requirements remain visible as downstream evidence gaps.</p></>:<div className="panel-empty">Create a replacement mission to use requirement-driven discovery. Manual screening remains available below.</div>}
    </section>

    <section className="command-panel" style={{marginBottom:20}}>
      <div className="panel-title-row"><div><span className="panel-kicker">Manual search controls</span><h2>Refine chemistry or run an independent screen</h2></div><span className="count-chip">{constraints.length} manual constraints</span></div>
      <form onSubmit={discover}><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(210px,1fr))",gap:14}}>
        <label><small>Required elements</small><input value={form.elements} onChange={e=>setForm({...form,elements:e.target.value})} placeholder="Si, O, Al"/></label>
        <label><small>Excluded elements</small><input value={form.excludeElements} onChange={e=>setForm({...form,excludeElements:e.target.value})}/></label>
        <label><small>Chemical system</small><input value={form.chemsys} onChange={e=>setForm({...form,chemsys:e.target.value})} placeholder="Si-O"/></label>
        <label><small>Formula</small><input value={form.formula} onChange={e=>setForm({...form,formula:e.target.value})} placeholder="SiO2"/></label>
        <label><small>Minimum band gap (eV)</small><input type="number" step="any" value={form.minBandGap} onChange={e=>setForm({...form,minBandGap:e.target.value})}/></label>
        <label><small>Maximum density (g/cm³)</small><input type="number" step="any" value={form.maxDensity} onChange={e=>setForm({...form,maxDensity:e.target.value})}/></label>
        <label><small>Maximum energy above hull (eV/atom)</small><input type="number" step="any" value={form.maxHull} onChange={e=>setForm({...form,maxHull:e.target.value})}/></label>
        <label><small>Minimum bulk modulus (GPa)</small><input type="number" step="any" value={form.minBulk} onChange={e=>setForm({...form,minBulk:e.target.value})}/></label>
        <label><small>Minimum shear modulus (GPa)</small><input type="number" step="any" value={form.minShear} onChange={e=>setForm({...form,minShear:e.target.value})}/></label>
        <label><small>Maximum candidates</small><input type="number" min={1} max={100} value={form.limit} onChange={e=>setForm({...form,limit:Number(e.target.value)||25})}/></label>
      </div><div style={{display:"flex",gap:14,alignItems:"center",marginTop:18,flexWrap:"wrap"}}><label style={{display:"flex",gap:8,alignItems:"center"}}><input type="checkbox" checked={form.stableOnly} onChange={e=>setForm({...form,stableOnly:e.target.checked})}/><span>Stable materials only</span></label><button className="btn" disabled={loading||constraints.length===0}>{loading?"Searching…":"Run manual screen"}</button><button className="btn btn-secondary" type="button" onClick={()=>{setForm(initial);setError("");resetResults()}}>Reset</button></div></form>
      <p className="muted" style={{marginTop:14}}>Materials Project values remain <strong>computed database evidence</strong>. They are not experimental measurements, validation, or acceptance decisions.</p>{error&&<div className="panel-empty"><strong>Discovery unavailable.</strong><p>{error}</p></div>}
    </section>

    {result?.mission_context&&<section className="command-panel" style={{marginBottom:20}}><div className="panel-title-row"><div><span className="panel-kicker">Mission translation audit</span><h2>{result.mission_context.project_name}</h2><p className="muted">Baseline: {result.mission_context.baseline_material_name||result.mission_context.baseline_material_id}</p></div><span className="count-chip">{pct(result.mission_context.hard_constraint_coverage)} hard-gate coverage</span></div><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:12}}><div><small>Hard requirements</small><strong style={{display:"block",fontSize:24}}>{result.mission_context.hard_constraint_count}</strong></div><div><small>Hard represented</small><strong style={{display:"block",fontSize:24}}>{result.mission_context.hard_constraints_represented}</strong></div><div><small>Soft priorities</small><strong style={{display:"block",fontSize:24}}>{result.mission_context.soft_constraint_count??0}</strong></div><div><small>Soft represented</small><strong style={{display:"block",fontSize:24}}>{result.mission_context.soft_preferences_represented??0}</strong></div><div><small>Explicit gaps</small><strong style={{display:"block",fontSize:24}}>{result.mission_context.unsupported_constraints.length}</strong></div></div>{result.mission_context.unsupported_constraints.length>0&&<div style={{marginTop:14}}><strong>Downstream evidence gaps</strong>{result.mission_context.unsupported_constraints.slice(0,8).map(row=><p className="muted" key={row.constraint_id}><code>{row.property_key}</code> · {readableReason(row.reason)}{row.detail?` — ${row.detail}`:""}</p>)}</div>}<p className="muted">{result.mission_context.search_semantics}</p></section>}

    {result&&<>
      <section className="decision-outcome-kpis" style={{marginBottom:20}}><article className="neutral"><small>Screened</small><strong>{result.records_screened}</strong><span>External records</span></article><article className="advance"><small>Returned</small><strong>{result.candidates_returned}</strong><span>Ranked candidates</span></article><article className="hold"><small>Unresolved</small><strong>{result.candidates.filter(c=>c.constraint_summary.unknown>0).length}</strong><span>Need evidence</span></article><article className="reject"><small>Failures</small><strong>{result.candidates.filter(c=>c.constraint_summary.fail>0).length}</strong><span>Hard violations</span></article></section>

      <section className="command-panel" style={{marginBottom:20}}><div className="panel-title-row"><div><span className="panel-kicker">Evidence-aware comparison</span><h2>Compare the candidates worth spending validation effort on</h2></div><span className="count-chip">{compareIds.length}/5 selected</span></div><p className="muted">Select 2–5 candidates below. Comparison keeps hard-gate failures, unresolved evidence, soft priorities, source provenance, stability, and computed property values separate instead of collapsing them into one opaque score.</p>{compareIds.length===5&&<p className="warn">Comparison limit reached. Remove one candidate to select another.</p>}</section>

      {compared.length>=2&&<section className="command-panel" style={{marginBottom:20,overflowX:"auto"}}><div className="panel-title-row"><div><span className="panel-kicker">Side-by-side evidence matrix</span><h2>{compared.length} candidate comparison</h2></div><button className="btn btn-secondary" type="button" onClick={()=>setCompareIds([])}>Clear comparison</button></div><table style={{width:"100%",borderCollapse:"collapse",minWidth:760}}><thead><tr><th style={{textAlign:"left",padding:10}}>Criterion</th>{compared.map(c=><th key={c.material_id} style={{textAlign:"left",padding:10}}><strong>#{c.rank} {candidateName(c)}</strong><div className="muted">{c.material_id}</div></th>)}</tr></thead><tbody>
        <tr><td style={{padding:10}}><strong>Screen state</strong></td>{compared.map(c=><td key={c.material_id} style={{padding:10}}><b className={`cell-state ${c.constraint_summary.fail?"fail":c.constraint_summary.unknown?"unknown":"pass"}`}>{screeningState(c)}</b></td>)}</tr>
        <tr><td style={{padding:10}}>Hard PASS / FAIL / UNKNOWN</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{c.constraint_summary.pass} / {c.constraint_summary.fail} / {c.constraint_summary.unknown}</td>)}</tr>
        <tr><td style={{padding:10}}>Hard evidence coverage</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{pct(c.constraint_summary.evidence_coverage)}</td>)}</tr>
        <tr><td style={{padding:10}}>Soft satisfied / failed / unresolved weight</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{c.preference_summary?.total_weight?`${c.preference_summary.pass_weight} / ${c.preference_summary.fail_weight} / ${c.preference_summary.unknown_weight}`:"—"}</td>)}</tr>
        <tr><td style={{padding:10}}>Stability / theory status</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{c.is_stable===true?"stable":c.is_stable===false?"not source-stable":"unknown"} · {c.is_theoretical===true?"theoretical":c.is_theoretical===false?"non-theoretical":"unknown"}</td>)}</tr>
        <tr><td style={{padding:10}}>MP provenance references</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{c.materials_project_origins.length}</td>)}</tr>
        {compareProperties.map(([key,label,unit])=><tr key={key}><td style={{padding:10}}>{label}</td>{compared.map(c=><td key={c.material_id} style={{padding:10}}>{fmt(observation(c,key),unit)}</td>)}</tr>)}
      </tbody></table><p className="muted" style={{marginTop:14}}>A missing value is displayed as — and remains unknown. This matrix does not impute values or convert computed-database evidence into experimental evidence.</p></section>}

      <section className="command-panel" style={{marginBottom:20}}><div className="panel-title-row"><div><span className="panel-kicker">Ranking contract</span><h2>Why this order is auditable</h2></div><span className="count-chip">{readableReason(result.ranking_policy.type)}</span></div><div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{result.ranking_policy.order.map((step,index)=><span className="count-chip" key={step}>{index+1}. {readableReason(step)}</span>)}</div>{result.ranking_policy.soft_weight_semantics&&<p className="muted" style={{marginTop:12}}>{result.ranking_policy.soft_weight_semantics}</p>}</section>

      <section className="command-panel" style={{marginBottom:20}}><div className="panel-title-row"><div><span className="panel-kicker">Candidate admission</span><h2>{selectedProject?`Add reviewed candidates to ${selectedProject.name}`:"Choose a replacement mission"}</h2></div><span className="count-chip">explicit write step</span></div>{projects.length?<div style={{display:"flex",gap:12,alignItems:"end",flexWrap:"wrap"}}><label style={{minWidth:300}}><small>Replacement project</small><select value={projectId} onChange={e=>setProjectId(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{projectId&&<Link className="btn btn-secondary" href={`/projects/${projectId}/replacement`}>Open mission</Link>}</div>:<p className="muted">Create a replacement project before adopting candidates.</p>}<p className="muted">Adoption re-fetches the Materials Project record server-side and preserves its source snapshot/provenance chain. Preview values are never trusted as write input.</p>{adoptError&&<div className="panel-empty"><strong>Adoption failed.</strong><p>{adoptError}</p></div>}</section>

      <section style={{display:"grid",gap:16}}>{result.candidates.map((c,index)=>{const s=c.constraint_summary,a=adopted[c.material_id],soft=c.preference_summary,previous=index>0?result.candidates[index-1]:undefined,selected=compareIds.includes(c.material_id);return <article className="command-panel" key={c.material_id}><div className="panel-title-row"><div><span className="panel-kicker">#{c.rank} · {c.material_id}</span><h2>{candidateName(c)}</h2><p className="muted">{c.chemical_formula||"formula unavailable"} · {c.crystal_system||"crystal system unknown"} {c.space_group_symbol?`· ${c.space_group_symbol}`:""}</p></div><span className={`count-chip ${s.fail?"reject":s.unknown?"hold":"advance"}`}>{screeningState(c)}</span></div>
        <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap",marginBottom:14}}><button className={selected?"btn":"btn btn-secondary"} type="button" disabled={!selected&&compareIds.length>=5} onClick={()=>toggleCompare(c.material_id)}>{selected?"✓ Selected for comparison":"Compare candidate"}</button><span className="muted">Select 2–5 to open the side-by-side matrix.</span></div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10,margin:"12px 0"}}><div><small>Hard PASS</small><strong style={{display:"block",fontSize:22}}>{s.pass}</strong></div><div><small>Hard FAIL</small><strong style={{display:"block",fontSize:22}}>{s.fail}</strong></div><div><small>Hard UNKNOWN</small><strong style={{display:"block",fontSize:22}}>{s.unknown}</strong></div><div><small>Hard evidence</small><strong style={{display:"block",fontSize:22}}>{pct(s.evidence_coverage)}</strong></div>{soft&&soft.total_weight>0&&<><div><small>Soft satisfied weight</small><strong style={{display:"block",fontSize:22}}>{soft.pass_weight}/{soft.total_weight}</strong></div><div><small>Soft unresolved weight</small><strong style={{display:"block",fontSize:22}}>{soft.unknown_weight}</strong></div></>}</div>
        <div className="panel-empty" style={{textAlign:"left",marginBottom:14}}><strong>Why rank #{c.rank}?</strong><p>{rankingExplanation(c,previous)}</p></div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10,marginBottom:14}}>{compareProperties.slice(0,6).map(([key,label,unit])=><div key={key}><small>{label}</small><div>{fmt(observation(c,key),unit)}</div></div>)}</div>
        <div className="requirement-mini-table"><div><span>Hard requirement</span><span>Screening result</span></div>{c.constraint_evaluations.map((r,i)=><div key={`${r.property}-${i}`}><span>{r.property}{r.minimum!==null?` ≥ ${r.minimum}`:""}{r.maximum!==null?` ≤ ${r.maximum}`:""}{r.value!==null?` · observed ${Number(r.value.toFixed(4))}`:" · no value"}</span><b className={`cell-state ${r.status}`}>{r.status.toUpperCase()}</b></div>)}</div>
        {(c.preference_evaluations?.length??0)>0&&<div style={{marginTop:14}}><strong>Soft preference audit</strong><div className="requirement-mini-table" style={{marginTop:8}}><div><span>Mission preference</span><span>Weighted result</span></div>{c.preference_evaluations?.map((r,i)=><div key={`${r.constraint_id||r.property}-${i}`}><span>{r.description||r.property} · w={r.weight}{r.value!==null?` · observed ${Number(r.value.toFixed(4))}`:" · no value"}</span><b className={`cell-state ${r.status}`}>{r.status.toUpperCase()}</b></div>)}</div></div>}
        <div style={{display:"flex",gap:12,alignItems:"center",marginTop:14,flexWrap:"wrap"}}>{a?<><span className="good">✓ {a.attached?"Added to mission":"Already in mission"}</span><Link href={`/projects/${a.project_id}/replacement`}>Review candidate →</Link></>:<button className="btn" disabled={!projectId||adopting===c.material_id} onClick={()=>adopt(c)}>{adopting===c.material_id?"Re-fetching & preserving provenance…":"Add to selected mission"}</button>}<span className="muted">MP provenance refs: {c.materials_project_origins.length}</span></div>
      </article>})}{!result.candidates.length&&<div className="command-panel panel-empty">No candidates matched this search.</div>}</section>
    </>}
  </div>;
}
