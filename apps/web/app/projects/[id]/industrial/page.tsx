"use client";
import {use, useState} from "react";
import Link from "next/link";
import {useMutation, useQuery} from "@tanstack/react-query";
import {
  api, CandidatePage, IndustrialConstraint, IndustrialEvidence, ManufacturingRoute,
  ViabilityComparison,
} from "@/lib/api";
import {IndustrialStateBadge} from "@/components/IndustrialStateBadge";
import {IndustrialSeparationNotice} from "@/components/IndustrialSeparationNotice";
import {EvidenceQualifiers} from "@/components/EvidenceQualifiers";

const DIMENSION_LABELS: Record<string,string> = {
  scientific_suitability: "Scientific suitability",
  manufacturing_compatibility: "Manufacturing compatibility",
  economic_feasibility: "Economic feasibility",
  supply_resilience: "Supply resilience",
  environmental_evidence: "Environmental evidence",
  regulatory_compatibility: "Regulatory compatibility",
  technology_maturity: "Technology maturity",
  experimental_validation: "Experimental validation",
};

export default function IndustrialViabilityWorkspace({params}:{params:Promise<{id:string}>}){
  const {id: projectId} = use(params);
  const candidates = useQuery({queryKey:["candidate-lab",projectId],queryFn:()=>api<CandidatePage>(`/replacement-projects/${projectId}/candidate-lab?offset=0&limit=200`)});
  const routes = useQuery({queryKey:["ind-routes"],queryFn:()=>api<ManufacturingRoute[]>("/industrial/manufacturing-routes")});
  const constraints = useQuery({
    queryKey:["ind-constraints",projectId],
    queryFn:()=>api<IndustrialConstraint[]>(`/projects/${projectId}/industrial-constraints`),
  });

  const [selected,setSelected]=useState<string[]>([]);
  const [comparison,setComparison]=useState<ViabilityComparison|null>(null);
  const [expanded,setExpanded]=useState<string|null>(null);
  const [useComposite,setUseComposite]=useState(false);

  const candidateItems = candidates.data?.items??[];
  const targets = selected.length>0 ? selected : candidateItems.slice(0,2).map(c=>c.id);
  const compare = useMutation({
    mutationFn:()=>api<ViabilityComparison>("/industrial/viability/compare",{method:"POST",body:JSON.stringify({
      project_id:projectId,
      targets:targets.map(candidateId=>{
        const c=candidateItems.find(item=>item.id===candidateId)!;
        return {candidate_id:candidateId,target_kind:c.candidate_kind,target_id:c.candidate_kind==="known_material"?c.material_id!:c.hypothesis_id!};
      }),
      ...(useComposite?{composite_methodology:"declared_weighted_mean_v1"}:{}),
    })}),
    onSuccess:setComparison,
  });

  const expandedCandidate=candidateItems.find(c=>c.id===expanded);
  const expandedTargetId=expandedCandidate?(expandedCandidate.candidate_kind==="known_material"?expandedCandidate.material_id:expandedCandidate.hypothesis_id):undefined;
  const detailTarget = comparison?.candidates.find(c=>c.target_id===expandedTargetId) ?? null;
  const evidence = useQuery({
    queryKey:["ind-evidence",expanded,expandedTargetId], enabled:!!expandedCandidate&&!!expandedTargetId,
    queryFn:()=>api<IndustrialEvidence[]>(`/industrial/evidence?target_kind=${expandedCandidate!.candidate_kind}&target_id=${expandedTargetId}`),
  });

  if(candidates.isLoading) return <div className="empty">Loading Industrial Viability Workspace…</div>;
  return <div className="grid">
    <div className="topline">
      <div>
        <div className="eyebrow">Industrial Viability · Phase 7</div>
        <h1>Can this actually be made, bought and shipped?</h1>
        <div className="muted">Scientific feasibility is not industrial feasibility. Each dimension is assessed separately and reported with its evidence.</div>
      </div>
      <div style={{display:"flex",gap:8}}>
        <Link className="btn btn-secondary" href={`/projects/${projectId}`}>Project</Link>
        <Link className="btn btn-secondary" href="/simulation">Simulation Lab</Link>
      </div>
    </div>
    <IndustrialSeparationNotice/>

    <div className="card card-pad">
      <div className="eyebrow">Candidates to compare</div>
      <div className="grid grid-2">
        <div>
          {candidateItems.map(c=>{
            const on = targets.includes(c.id);
            return <label key={c.id} className="muted" style={{display:"block",padding:"3px 0"}}>
              <input type="checkbox" checked={on} onChange={e=>{
                setSelected(e.target.checked ? [...new Set([...targets,c.id])] : targets.filter(t=>t!==c.id));
                setComparison(null);
              }}/> {c.display_name} · {c.candidate_kind}
            </label>;
          })}
        </div>
        <div className="notice">
          <strong>Composite score</strong>
          <label className="muted" style={{display:"block",marginTop:4}}>
            <input type="checkbox" checked={useComposite} onChange={e=>{setUseComposite(e.target.checked);setComparison(null);}}/>
            {" "}Compute a composite score using the declared weighted-mean methodology
          </label>
          <div className="muted" style={{marginTop:6}}>A composite appears only with an explicit methodology. Unknown and insufficient-evidence dimensions are excluded from it — never scored as zero — and the result stays marked partial so the exclusion is visible.</div>
        </div>
      </div>
      <div style={{marginTop:10}}>
        <button className="btn" disabled={compare.isPending||targets.length===0} onClick={()=>compare.mutate()}>
          Assess industrial viability
        </button>
      </div>
      {compare.error&&<div className="notice fail" style={{marginTop:8}}>{(compare.error as Error).message}</div>}
    </div>

    {comparison&&<div className="card">
      <div className="card-pad">
        <div className="eyebrow">Dimension comparison</div>
        <h2>Why each candidate stands where it does</h2>
        <p className="muted">{comparison.comparability_note}</p>
      </div>
      <div className="table-wrap"><table>
        <thead><tr>
          <th>Dimension</th>
          {comparison.candidates.map(c=><th key={c.target_id}>{c.target_display_name}</th>)}
        </tr></thead>
        <tbody>
          {comparison.dimensions.map(dim=><tr key={dim}>
            <td><strong>{DIMENSION_LABELS[dim]??dim}</strong></td>
            {comparison.candidates.map(c=><td key={c.target_id}>
              <IndustrialStateBadge state={c.dimension_states[dim]}/>
              <div className="muted" style={{fontSize:11,marginTop:3}}>
                {(c.dimension_details[dim]?.constraint_results??[]).slice(0,2).map((r,i)=>
                  <div key={i}>• {r.detail?.slice(0,110)}</div>)}
                {c.dimension_details[dim]?.detail&&<div>• {c.dimension_details[dim]?.detail}</div>}
              </div>
            </td>)}
          </tr>)}
          <tr>
            <td><strong>Overall</strong></td>
            {comparison.candidates.map(c=><td key={c.target_id}>
              <IndustrialStateBadge state={c.overall_state}/>
              {c.composite_score!=null&&<div className="muted" style={{fontSize:11}}>
                composite {c.composite_score.toFixed(3)} ({c.composite_methodology})
                {c.composite_is_partial&&<> · <strong>partial — {c.unknown_dimensions.length} dimension(s) excluded</strong></>}
              </div>}
              <div style={{marginTop:5}}>
                <button className="btn btn-secondary" style={{fontSize:11,padding:"2px 8px"}}
                        onClick={()=>{const item=candidateItems.find(x=>(x.candidate_kind==="known_material"?x.material_id:x.hypothesis_id)===c.target_id);setExpanded(expanded===item?.id?null:item?.id??null)}}>
                  {expanded&&expandedTargetId===c.target_id?"hide detail":"why?"}
                </button>
              </div>
            </td>)}
          </tr>
        </tbody>
      </table></div>
    </div>}

    {detailTarget&&<div className="card card-pad">
      <div className="eyebrow">Explanation</div>
      <h2>{detailTarget.target_display_name} — <IndustrialStateBadge state={detailTarget.overall_state}/></h2>
      <div className="muted">Declared composition: {detailTarget.declared_elements.join(", ")||"not recorded"} · maturity {detailTarget.maturity_stage} · checksum <code>{detailTarget.assessment_checksum.slice(0,16)}…</code></div>

      {detailTarget.hard_constraint_failures.length>0&&<div className="notice fail" style={{marginTop:10}}>
        <strong>Hard constraint failures</strong>
        {detailTarget.hard_constraint_failures.map(f=><div key={f.constraint_id} className="muted">• {f.display_label}: {f.detail}</div>)}
      </div>}

      {detailTarget.missing_evidence.length>0&&<div className="notice" style={{marginTop:10}}>
        <strong>What is not known</strong>
        <div className="muted">These constraints could not be evaluated. They are not failures, and they are not passes.</div>
        {detailTarget.missing_evidence.map(m=><div key={m.constraint_id} className="muted">• [{m.state}] {m.display_label} — {m.detail}</div>)}
      </div>}

      {detailTarget.conflicting_evidence.length>0&&<div className="notice fail" style={{marginTop:10}}>
        <strong>Contradictory evidence</strong>
        <div className="muted">Both records are retained. Neither is deleted and the newer one does not automatically win.</div>
        {detailTarget.conflicting_evidence.map((c,i)=><div key={i} className="muted">• {String(c.detail)}</div>)}
      </div>}

      <div className="notice" style={{marginTop:10}}>
        <strong>Evidence coverage</strong>
        <div className="muted">
          {detailTarget.evidence_coverage.total_records} record(s) ·
          {" "}{detailTarget.evidence_coverage.stale_records} stale ·
          {" "}{detailTarget.evidence_coverage.estimate_records} estimate(s)
        </div>
        {detailTarget.evidence_coverage.dimensions_with_no_evidence.length>0&&
          <div className="muted">No evidence at all for: {detailTarget.evidence_coverage.dimensions_with_no_evidence.join(", ")}</div>}
      </div>

      {evidence.data&&evidence.data.length>0&&<div className="table-wrap" style={{marginTop:12}}><table>
        <thead><tr><th>Metric</th><th>Value</th><th>Qualifiers</th><th>Category</th></tr></thead>
        <tbody>{evidence.data.map(e=><tr key={e.id}>
          <td><strong>{e.display_label}</strong><div className="muted">{e.metric_key}</div></td>
          <td>{e.numeric_value!=null?`${e.numeric_value} ${e.unit??""}`:
               e.boolean_value!=null?String(e.boolean_value):
               e.categorical_value??"—"}
              {e.lower_bound!=null&&e.upper_bound!=null&&<div className="muted">range {e.lower_bound}–{e.upper_bound}</div>}</td>
          <td><EvidenceQualifiers evidence={e}/></td>
          <td>{e.category}</td>
        </tr>)}</tbody>
      </table></div>}
    </div>}

    <div className="grid grid-2">
      <div className="card">
        <div className="card-pad"><div className="eyebrow">Industrial constraints</div><h2>What this project requires</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Requirement</th><th>Kind</th><th>Strength</th><th>If evidence is missing</th></tr></thead>
          <tbody>{constraints.data?.map(c=><tr key={c.id}>
            <td><strong>{c.display_label}</strong><div className="muted">{c.category}{c.metric_key?` · ${c.metric_key}`:""}</div></td>
            <td>{c.constraint_kind}
              {c.target_value!=null&&<div className="muted">{c.target_value}{c.target_unit?` ${c.target_unit}`:""}
                {c.currency&&<> ({c.currency} {c.currency_year}, {c.cost_basis})</>}</div>}</td>
            <td><span className="badge">{c.strength}</span></td>
            <td className="muted">{c.treat_missing_evidence_as}</td>
          </tr>)}</tbody>
        </table></div>
      </div>

      <div className="card">
        <div className="card-pad"><div className="eyebrow">Manufacturing routes</div><h2>How things get made</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Route</th><th>Family</th><th>Process window</th><th>Maturity</th></tr></thead>
          <tbody>{routes.data?.map(r=><tr key={r.id}>
            <td><strong>{r.display_name}</strong><div className="muted">{r.key}</div></td>
            <td>{r.process_family}</td>
            <td className="muted">{r.process_temperature_k_min!=null?`${r.process_temperature_k_min}–${r.process_temperature_k_max} K`:"not recorded"}</td>
            <td><span className="badge">{r.process_maturity}</span></td>
          </tr>)}</tbody>
        </table></div>
      </div>
    </div>
  </div>;
}
