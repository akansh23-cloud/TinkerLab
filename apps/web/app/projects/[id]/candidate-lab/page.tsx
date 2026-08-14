"use client";
import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api, CandidatePage, CandidateSearchSpace, GenerationPreview, GenerationRun, GenerationStrategy,
  ProjectDetail, SearchSpaceValidation, Specification, SubstitutionRule,
} from "@/lib/api";
import { GenerationRunSummary } from "@/components/GenerationRunSummary";
import { HypothesisWarning } from "@/components/HypothesisWarning";

export default function CandidateLabPage({params}:{params:Promise<{id:string}>}) {
  const {id}=use(params); const qc=useQueryClient();
  const project=useQuery({queryKey:["project",id],queryFn:()=>api<ProjectDetail>(`/replacement-projects/${id}`)});
  const spec=useQuery({queryKey:["spec",id],queryFn:()=>api<Specification>(`/replacement-projects/${id}/specification`)});
  const spaces=useQuery({queryKey:["search-spaces",id],queryFn:()=>api<CandidateSearchSpace[]>(`/replacement-projects/${id}/search-spaces`)});
  const rules=useQuery({queryKey:["substitution-rules",id],queryFn:()=>api<SubstitutionRule[]>(`/replacement-projects/${id}/substitution-rules`)});
  const strategies=useQuery({queryKey:["generation-strategies"],queryFn:()=>api<GenerationStrategy[]>(`/candidate-generation/strategies`)});
  const runs=useQuery({queryKey:["generation-runs",id],queryFn:()=>api<GenerationRun[]>(`/replacement-projects/${id}/generation-runs`)});
  const candidates=useQuery({queryKey:["candidate-lab",id],queryFn:()=>api<CandidatePage>(`/replacement-projects/${id}/candidate-lab?offset=0&limit=100`)});
  const active=useMemo(()=>spaces.data?.find(x=>x.active) ?? spaces.data?.[0],[spaces.data]);
  const [strategy,setStrategy]=useState("bounded_composition_variation"); const [seed,setSeed]=useState(42); const [budget,setBudget]=useState(20);
  const [validation,setValidation]=useState<SearchSpaceValidation|null>(null); const [preview,setPreview]=useState<GenerationPreview|null>(null);
  const validate=useMutation({mutationFn:()=>api<SearchSpaceValidation>(`/replacement-projects/${id}/search-spaces/${active!.id}/validate?strategy_key=${encodeURIComponent(strategy)}`,{method:"POST"}),onSuccess:setValidation});
  const previewRun=useMutation({mutationFn:()=>api<GenerationPreview>(`/replacement-projects/${id}/generation-runs/preview`,{method:"POST",body:JSON.stringify({search_space_id:active!.id,strategy_key:strategy,random_seed:seed,candidate_budget:budget,configuration:{source:"candidate_lab_ui"}})}),onSuccess:setPreview});
  const execute=useMutation({mutationFn:()=>api<GenerationRun>(`/replacement-projects/${id}/generation-runs`,{method:"POST",body:JSON.stringify({search_space_id:active!.id,strategy_key:strategy,random_seed:seed,candidate_budget:budget,configuration:{source:"candidate_lab_ui"},created_by:project.data!.created_by})}),onSuccess:async()=>{await Promise.all([qc.invalidateQueries({queryKey:["generation-runs",id]}),qc.invalidateQueries({queryKey:["candidate-lab",id]})]);}});
  if(project.isLoading||spaces.isLoading) return <div className="empty">Loading Candidate Lab…</div>;
  if(project.error||!project.data) return <div className="empty">Candidate Lab unavailable: {(project.error as Error)?.message}</div>;
  return <div className="grid">
    <div className="topline"><div><div className="eyebrow">Candidate Lab · Phase 5</div><h1>{project.data.name}</h1><div className="muted">Baseline: <Link href={`/materials/${project.data.baseline_material.id}`}>{project.data.baseline_material.display_name}</Link></div></div><div style={{display:"flex",gap:8}}><Link className="btn" href={`/projects/${id}/virtual-lab`}>Virtual Experiment Lab</Link><Link className="btn btn-secondary" href={`/projects/${id}/prediction-lab`}>Prediction Lab</Link><Link className="btn btn-secondary" href={`/projects/${id}/validation`}>Validation</Link><Link className="btn btn-secondary" href={`/projects/${id}`}>Back to project</Link></div></div>
    <HypothesisWarning/>
    <div className="grid grid-2">
      <div className="card card-pad"><h2>Generation inputs</h2><div><span className="kicker">Replacement specification</span><p><code>{spec.data?.checksum ?? "…"}</code></p></div><div><span className="kicker">Active search space</span><p>{active?`v${active.version} · ${active.checksum.slice(0,18)}…`:"No search space"}</p></div><div><span className="kicker">Candidate budget</span><p>{active?.candidate_budget ?? "—"} configured · hard local maximum 1,000</p></div></div>
      <div className="card card-pad"><h2>Candidate inventory</h2><p>{candidates.data?.total ?? 0} total project candidates</p><p className="muted">Known materials keep Phase-2 evidence. Hypotheses carry only proposed structure/process data, fingerprint and lineage.</p></div>
    </div>

    {active && <div className="card"><div className="card-pad"><div className="topline"><div><div className="eyebrow">Search Space Builder</div><h2>Version {active.version} {active.active&&<span className="badge pass">Active</span>}</h2></div><button className="btn btn-secondary" disabled={validate.isPending} onClick={()=>validate.mutate()}>Validate search space</button></div><p className="muted">Only these curator-defined dimensions may change. A new version is required for edits after execution.</p></div>
      <div className="table-wrap"><table><thead><tr><th>Component</th><th>Role</th><th>Control</th><th>Range</th><th>Guards</th></tr></thead><tbody>{active.component_rules.map(r=><tr key={r.id}><td><strong>{r.display_name}</strong><div className="muted"><code>{r.component_key}</code></div></td><td>{r.role??"—"}</td><td>{r.locked?"Locked":r.mutable?"Mutable":"Fixed"}</td><td>{r.mutable?`${r.min_amount}–${r.max_amount} ${r.amount_unit??""} step ${r.step_amount??"—"}`:"—"}</td><td>{[r.required&&"required",r.prohibited&&"prohibited",active.balance_component_key===r.component_key&&"balance"].filter(Boolean).join(" · ")||"—"}</td></tr>)}</tbody></table></div>
      {active.process_rules.length>0&&<div className="table-wrap"><table><thead><tr><th>Process variable</th><th>Bounds</th><th>Operational status</th></tr></thead><tbody>{active.process_rules.map(r=><tr key={r.id}><td>{r.display_name}<div className="muted"><code>{r.parameter_key}</code></div></td><td>{r.min_value}–{r.max_value} {r.unit} · step {r.step_value??"—"}</td><td><span className="badge">Data-level hypothesis only</span></td></tr>)}</tbody></table></div>}
      {validation&&<div className="card-pad"><div className={`notice ${validation.valid?"":"fail"}`}><strong>{validation.valid?"Search space valid":"Search space blocked"}</strong> · estimated cardinality {validation.estimated_cardinality}{validation.issues.map(x=><div key={`${x.code}-${x.path}`} className="muted">{x.severity.toUpperCase()} · {x.code} · {x.path}: {x.message}</div>)}</div></div>}
    </div>}

    <div className="card card-pad"><div className="eyebrow">Generation Preview</div><h2>Bounded deterministic run</h2><div className="grid grid-2">
      <label>Strategy<select value={strategy} onChange={e=>{setStrategy(e.target.value);setPreview(null);setValidation(null)}}>{strategies.data?.filter(s=>s.key!=="manual_hypothesis").map(s=><option key={s.key} value={s.key}>{s.key} · v{s.version}</option>)}</select></label>
      <label>Random seed<input type="number" value={seed} onChange={e=>setSeed(Number(e.target.value))}/></label>
      <label>Candidate budget<input type="number" min={1} max={1000} value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label>
      <div><span className="kicker">Selected strategy</span><p className="muted">{strategies.data?.find(s=>s.key===strategy)?.description ?? "…"}</p></div>
    </div><div style={{display:"flex",gap:8,marginTop:14}}><button className="btn btn-secondary" disabled={!active||previewRun.isPending} onClick={()=>previewRun.mutate()}>Preview only</button><button className="btn" disabled={!active||!preview?.valid||execute.isPending} onClick={()=>execute.mutate()}>Execute bounded run</button></div>
      {preview&&<div className="notice" data-testid="generation-preview" style={{marginTop:14}}><strong>{preview.valid?"Preview valid":"Preview blocked"}</strong><div className="muted">Estimated {preview.estimated_cardinality} combinations · budget {preview.candidate_budget} · truncation {preview.expected_truncation?"yes":"no"}</div><div className="muted">spec <code>{preview.specification_checksum.slice(0,14)}…</code> · space <code>{preview.search_space_checksum.slice(0,14)}…</code> · seed {preview.random_seed}</div>{preview.issues.map(x=><div key={`${x.code}-${x.path}`}>{x.severity.toUpperCase()} · {x.code}: {x.message}</div>)}</div>}
      {execute.error&&<div className="notice fail" style={{marginTop:14}}>Run failed: {(execute.error as Error).message}</div>}
    </div>

    <div className="card"><div className="card-pad"><h2>Approved substitution rules</h2><p className="muted">Automatic substitution can use only curator-approved rules. Evidence may be absent in research/demo mode and is then explicitly curator-provided, not proven.</p></div><div className="table-wrap"><table><thead><tr><th>Source</th><th>Replacement</th><th>Status</th><th>Reason / evidence</th></tr></thead><tbody>{rules.data?.map(r=><tr key={r.id}><td><code>{r.source_component_key}</code></td><td>{r.replacement_display_name}<div className="muted"><code>{r.replacement_component_key}</code></div></td><td><span className="badge">{r.status}</span></td><td>{r.reason}<div className="muted">{r.evidence_id?`Evidence ${r.evidence_id}`:"Curator-provided; no scientific evidence attached"}</div></td></tr>)}</tbody></table></div></div>

    <div className="card"><div className="card-pad"><h2>Known materials + hypotheses</h2><p className="muted">No overall AI score. Known evidence and hypothesis uncertainty are shown as different states.</p></div><div className="table-wrap"><table><thead><tr><th>Candidate</th><th>Kind</th><th>Source</th><th>Changes</th><th>Hard constraints</th><th>Evidence / conflicts</th><th>Structural status</th><th>Lineage</th></tr></thead><tbody>{candidates.data?.items.map(c=><tr key={c.id}><td>{c.candidate_kind==="known_material"&&c.material_id?<Link href={`/materials/${c.material_id}`}><strong>{c.display_name}</strong></Link>:c.hypothesis_id?<Link href={`/candidate-hypotheses/${c.hypothesis_id}`}><strong>{c.display_name}</strong></Link>:c.display_name}<div className="muted">{c.evidence_posture}</div></td><td><span className="badge">{c.candidate_kind==="known_material"?"Known material":"Hypothesis"}</span></td><td>{c.candidate_source}</td><td>{c.change_count}</td><td><span className="muted">PASS {c.hard_passed} · FAIL {c.hard_failed} · UNKNOWN {c.hard_unknown}</span></td><td>{Math.round(c.evidence_completeness*100)}% constraint evidence<div className="muted">{c.scientific_conflicts} conflict(s)</div></td><td>{c.structural_validity??"n/a"}</td><td>{c.generation_run_id?<Link href={`/generation-runs/${c.generation_run_id}`}>Open run</Link>:"Manual / pre-existing"}</td></tr>)}</tbody></table></div></div>
    <div className="grid">{runs.data?.slice(0,4).map(r=><GenerationRunSummary key={r.id} run={r}/>)}</div>
  </div>;
}
