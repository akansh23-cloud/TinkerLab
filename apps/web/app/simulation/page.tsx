"use client";
import {useMemo, useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {
  api, MaterialSummary, Representation, RepresentationValidation, SimulationMethod,
  SimulationProvider, SimulationRoutePreview, SimulationWorkflow,
  SimulationWorkflowPreview,
} from "@/lib/api";
import {SimulationWarning} from "@/components/SimulationWarning";
import {RouteStatusBadge} from "@/components/RouteStatusBadge";

// The industrial framing below is method-level context (what a converged result of this method
// class is used for in industry). It is deliberately never a claim about the user's specific
// composition — those claims only come from converged, provenance-complete results.
const METHOD_INDUSTRY_CONTEXT: Record<string, string> = {
  analytical_fixture: "Software-validation only. Proves the pipeline (routing, snapshots, execution, parsing, convergence, checksums) is trustworthy before any real solver is relied on.",
  dft: "First-principles total energies underpin industrial screening for phase stability, defect energetics, battery voltages and catalyst surfaces — after convergence testing and experimental anchoring. A single converged energy is an input to that pipeline, not a product decision.",
  md: "Atomistic MD with validated potentials informs polymer processing windows, diffusion, and thermomechanical response in industrial R&D. The potential's provenance decides whether any of it is meaningful.",
  calphad: "CALPHAD phase equilibria drive real alloy design and heat-treatment schedules in metallurgy — but only on top of assessed, reviewed thermodynamic databases. Without one, no diagram is honest.",
  ml_force_field_future: "ML interatomic potentials promise near-DFT accuracy at MD cost for materials screening — contingent on licensed, validated weights with a declared applicability domain.",
};

const ELEMENT_ROWS: string[][] = [
  ["H","","","","","","","","","","","","","","","","","He"],
  ["Li","Be","","","","","","","","","","","B","C","N","O","F","Ne"],
  ["Na","Mg","","","","","","","","","","","Al","Si","P","S","Cl","Ar"],
  ["K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr"],
  ["Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe"],
  ["Cs","Ba","La","Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn"],
];

type Site = {element:string; fractional_coordinates:[number,number,number]};

export default function SimulationLabPage(){
  const router = useRouter();
  const qc = useQueryClient();
  const materials = useQuery({queryKey:["materials"],queryFn:()=>api<MaterialSummary[]>("/materials")});
  const providers = useQuery({queryKey:["sim-providers"],queryFn:()=>api<SimulationProvider[]>("/simulation/providers")});
  const methods = useQuery({queryKey:["sim-methods"],queryFn:()=>api<{methods:SimulationMethod[]}>("/simulation/methods")});
  const workflows = useQuery({queryKey:["sim-workflows"],queryFn:()=>api<SimulationWorkflow[]>("/simulation/workflows")});

  const [targetId,setTargetId]=useState("");
  const effectiveTarget = targetId || materials.data?.[0]?.id || "";
  const representations = useQuery({
    queryKey:["sim-representations",effectiveTarget], enabled:!!effectiveTarget,
    queryFn:()=>api<Representation[]>(`/simulation/targets/known_material/${effectiveTarget}/representations`),
  });
  const routes = useQuery({
    queryKey:["sim-routes",effectiveTarget], enabled:!!effectiveTarget,
    queryFn:()=>api<SimulationRoutePreview>("/simulation/routes/preview",{method:"POST",body:JSON.stringify({
      target_kind:"known_material", target_id:effectiveTarget, requested_purpose:"energy_stability"})}),
  });

  // --- Element Composer: assemble any periodic cell from real elements. The router then says,
  // honestly and in detail, what science that structure can and cannot support today. ---
  const [sites,setSites]=useState<Site[]>([{element:"C",fractional_coordinates:[0,0,0]},{element:"C",fractional_coordinates:[0.25,0.25,0.25]}]);
  const [lattice,setLattice]=useState(3.567);
  const [label,setLabel]=useState("Composer periodic cell");
  const [validation,setValidation]=useState<RepresentationValidation|null>(null);
  const composerContent = useMemo(()=>({
    lattice_vectors:[[lattice,0,0],[0,lattice,0],[0,0,lattice]], lattice_unit:"angstrom",
    sites: sites.map(s=>({element:s.element, fractional_coordinates:s.fractional_coordinates})),
  }),[sites,lattice]);
  const elementCounts = useMemo(()=>{const c:Record<string,number>={};for(const s of sites)c[s.element]=(c[s.element]??0)+1;return c;},[sites]);
  const addElement=(el:string)=>{
    if(!el)return;
    const n=sites.length;
    setSites([...sites,{element:el,fractional_coordinates:[((n*0.25)%1),((n*0.5)%1),((n*0.75)%1)]}]);
    setValidation(null);
  };
  const validate=useMutation({
    mutationFn:()=>api<RepresentationValidation>("/simulation/representations/validate",{method:"POST",body:JSON.stringify({
      representation_format:"periodic_structure_json_v1", content:composerContent})}),
    onSuccess:setValidation,
  });
  const attach=useMutation({
    mutationFn:()=>api<Representation>(`/materials/${effectiveTarget}/representations`,{method:"POST",body:JSON.stringify({
      label, representation_format:"periodic_structure_json_v1", content:composerContent, visibility:"private",
      provenance_note:"Authored in the Simulation Lab Element Composer; scientist-supplied structure, no atoms inferred."})}),
    onSuccess:async()=>{await qc.invalidateQueries({queryKey:["sim-representations",effectiveTarget]});await qc.invalidateQueries({queryKey:["sim-routes",effectiveTarget]});},
  });

  // --- run the software-validation fixture end-to-end when its route is ready ---
  const readyFixtureRoute = routes.data?.routes.find(r=>r.route_status==="ready"&&r.method_family==="analytical_fixture");
  const [preview,setPreview]=useState<SimulationWorkflowPreview|null>(null);
  const previewFixture=useMutation({
    mutationFn:()=>api<SimulationWorkflowPreview>("/simulation/workflows/preview",{method:"POST",body:JSON.stringify({
      target_kind:"known_material", target_id:effectiveTarget, method_key:readyFixtureRoute!.method_key,
      provider_version_id:readyFixtureRoute!.provider_version_id,
      parameters:{step_size:0.1,max_iterations:500,gradient_tolerance:1e-8}})}),
    onSuccess:setPreview,
  });
  const runFixture=useMutation({
    mutationFn:async()=>{
      const workflow=await api<SimulationWorkflow>("/simulation/workflows",{method:"POST",body:JSON.stringify({
        target_kind:"known_material", target_id:effectiveTarget, method_key:readyFixtureRoute!.method_key,
        provider_version_id:readyFixtureRoute!.provider_version_id,
        parameters:{step_size:0.1,max_iterations:500,gradient_tolerance:1e-8}, metadata:{source:"simulation_lab_ui"}})});
      return api<SimulationWorkflow>(`/simulation/workflows/${workflow.id}/execute`,{method:"POST"});
    },
    onSuccess:async w=>{await qc.invalidateQueries({queryKey:["sim-workflows"]});router.push(`/simulation/workflows/${w.id}`);},
  });

  if(materials.isLoading||providers.isLoading) return <div className="empty">Loading Simulation Lab…</div>;
  return <div className="grid">
    <div className="topline">
      <div>
        <div className="eyebrow">Simulation Lab · Phase 6</div>
        <h1>Physics &amp; Simulation Operating System</h1>
        <div className="muted">Route, execute and audit bounded physics workflows. Refusals are first-class scientific outcomes.</div>
      </div>
      <div style={{display:"flex",gap:8}}><Link className="btn btn-secondary" href="/materials">Materials</Link><Link className="btn btn-secondary" href="/">Projects</Link></div>
    </div>
    <SimulationWarning/>

    <div className="card card-pad">
      <div className="eyebrow">Target</div>
      <div className="grid grid-2">
        <label className="label">Known material
          <select className="select" value={effectiveTarget} onChange={e=>{setTargetId(e.target.value);setValidation(null);setPreview(null);}}>
            {materials.data?.map(m=><option key={m.id} value={m.id}>{m.display_name}</option>)}
          </select>
        </label>
        <div className="notice"><strong>Representation readiness</strong>
          <div className="muted">{representations.data?.length??0} representation(s) on file. Methods only route against a valid, complete representation of the type they require — a formulation name is never enough for DFT or MD.</div>
        </div>
      </div>
    </div>

    <div className="card card-pad">
      <div className="eyebrow">Element Composer</div>
      <h2>Experiment with any elements — the router answers honestly</h2>
      <p className="muted">Assemble a periodic cell from real elements. Validation checks syntax and structural completeness deterministically; the router then reports exactly which physics methods this structure can support, and precisely what is missing for the rest (for example an approved pseudopotential per element). Nothing is invented to make a route run.</p>
      <div className="table-wrap"><table><tbody>
        {ELEMENT_ROWS.map((row,i)=><tr key={i}>{row.map((el,j)=>
          <td key={j} style={{padding:2}}>{el?<button className="btn btn-secondary" style={{minWidth:34,padding:"3px 5px",fontSize:11}} onClick={()=>addElement(el)}>{el}</button>:null}</td>
        )}</tr>)}
      </tbody></table></div>
      <div className="grid grid-3" style={{marginTop:12}}>
        <label className="label">Cubic lattice parameter (angstrom)
          <input className="input" type="number" step={0.001} value={lattice} onChange={e=>{setLattice(Number(e.target.value));setValidation(null);}}/>
        </label>
        <label className="label">Representation label
          <input className="input" value={label} onChange={e=>setLabel(e.target.value)}/>
        </label>
        <div className="notice"><strong>Cell contents</strong>
          <div>{Object.entries(elementCounts).map(([el,n])=>`${el}×${n}`).join("  ")||"empty"}</div>
          <div className="muted">{sites.length} site(s) · <button className="btn btn-secondary" style={{padding:"1px 8px",fontSize:11}} onClick={()=>{setSites([]);setValidation(null);}}>clear</button></div>
        </div>
      </div>
      <div style={{marginTop:10,display:"flex",gap:8}}>
        <button className="btn" disabled={validate.isPending||sites.length===0} onClick={()=>validate.mutate()}>Validate structure</button>
        <button className="btn" disabled={attach.isPending||!validation?.usable} onClick={()=>attach.mutate()}>Attach to target &amp; re-route</button>
      </div>
      {validation&&<div className={`notice ${validation.usable?"":"fail"}`} style={{marginTop:10}}>
        <strong>{validation.validation_status} · {validation.completeness_status}</strong>
        <div className="muted">checksum {validation.normalized_checksum?.slice(0,16)??"—"} · {validation.atom_count??0} atoms · elements {validation.chemical_elements.join(", ")||"—"}</div>
        {validation.messages.map((m,i)=><div key={i} className="muted">• [{m.code}] {m.message}</div>)}
        {validation.usable&&<div className="muted">Structure is syntactically valid and structurally complete. Validity is structural — it is not a claim of chemical correctness or synthesizability.</div>}
      </div>}
      {attach.error&&<div className="notice fail" style={{marginTop:8}}>{(attach.error as Error).message}</div>}
    </div>

    <div className="card">
      <div className="card-pad"><div className="eyebrow">Route preview</div>
        <h2>What can science honestly say about this target?</h2>
        <p className="muted">Every method/provider pair is assessed with explicit reasons. A refusal here is the correct scientific answer, not a failure — it tells you exactly which representation or registered artifact would unlock the route.</p>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Method</th><th>Provider</th><th>Status</th><th>Fidelity</th><th>Why / what is missing</th><th>Industrial relevance of this method class</th></tr></thead>
        <tbody>{routes.data?.routes.map(r=><tr key={r.route_checksum}>
          <td><strong>{r.method_display_name}</strong><div className="muted">{r.method_key}</div></td>
          <td>{r.provider_display_name}<div className="muted">v{r.provider_version} · {r.adapter_key}</div></td>
          <td><RouteStatusBadge status={r.route_status}/></td>
          <td>{r.fidelity}<div className="muted">{r.estimated_resource_class}</div></td>
          <td>{r.reasons.slice(0,3).map((x,i)=><div key={i} className="muted">• {x.message}</div>)}
            {r.missing_artifact_types.length>0&&<div className="muted"><strong>Missing artifacts:</strong> {r.missing_artifact_types.join(", ")}</div>}</td>
          <td className="muted" style={{maxWidth:300}}>{METHOD_INDUSTRY_CONTEXT[r.method_family]??""}</td>
        </tr>)}</tbody>
      </table></div>
      {readyFixtureRoute&&<div className="card-pad">
        <div style={{display:"flex",gap:8}}>
          <button className="btn btn-secondary" disabled={previewFixture.isPending} onClick={()=>previewFixture.mutate()}>Preview ready workflow (executes nothing)</button>
          <button className="btn" disabled={runFixture.isPending} onClick={()=>runFixture.mutate()}>Create &amp; execute bounded workflow</button>
        </div>
        {preview&&<div className="notice" style={{marginTop:10}}>
          <strong>Workflow preview — nothing executed</strong>
          <div className="muted">input checksum <code>{preview.input_checksum?.slice(0,16)}…</code> · template {preview.workflow_template.key} v{preview.workflow_template.version} · steps: {preview.workflow_template.steps.join(" → ")}</div>
          <div className="muted">parser {preview.provider_version.parser.join(" v")} · builder {preview.provider_version.input_builder.join(" v")} · convergence {preview.provider_version.convergence_evaluator.join(" v")}</div>
          <div className="muted">normalized parameters: <code>{JSON.stringify(preview.normalized_parameters)}</code></div>
        </div>}
        {runFixture.error&&<div className="notice fail" style={{marginTop:8}}>{(runFixture.error as Error).message}</div>}
      </div>}
    </div>

    <div className="card">
      <div className="card-pad"><div className="eyebrow">Providers</div><h2>Honest availability</h2></div>
      <div className="table-wrap"><table>
        <thead><tr><th>Provider</th><th>Family</th><th>Mode</th><th>Status</th></tr></thead>
        <tbody>{providers.data?.map(p=><tr key={p.id}>
          <td><strong>{p.display_name}</strong><div className="muted">{p.description}</div></td>
          <td>{p.method_family}</td><td>{p.approved_execution_mode}</td>
          <td><span className="badge">{p.status}</span></td>
        </tr>)}</tbody>
      </table></div>
    </div>

    <div className="card">
      <div className="card-pad"><div className="eyebrow">Workflow history</div><h2>Auditable simulation workflows</h2></div>
      <div className="table-wrap"><table>
        <thead><tr><th>Workflow</th><th>Method / fidelity</th><th>Status</th><th>Checksum</th></tr></thead>
        <tbody>{workflows.data?.map(w=><tr key={w.id}>
          <td><Link href={`/simulation/workflows/${w.id}`}><strong>{w.id.slice(0,8)}…</strong></Link><div className="muted">{w.target_kind}</div></td>
          <td>{w.requested_purpose}<div className="muted">{w.requested_fidelity}</div></td>
          <td><span className="badge">{w.status}</span>{w.failure_code&&<div className="muted">{w.failure_code}</div>}</td>
          <td><code>{w.workflow_checksum?.slice(0,14)??"—"}…</code></td>
        </tr>)}</tbody>
      </table></div>
    </div>

    {methods.data&&<div className="card card-pad"><div className="eyebrow">Method registry</div>
      <div className="grid grid-3">{methods.data.methods.map(m=><div className="notice" key={m.key}>
        <strong>{m.display_name}</strong>
        <div className="muted">{m.method_family} · {m.fidelity}</div>
        <div className="muted">outputs: {m.output_property_keys.join(", ")||"—"}</div>
        {m.known_limitations.slice(0,2).map((l,i)=><div key={i} className="muted">• {l}</div>)}
      </div>)}</div>
    </div>}
  </div>;
}
