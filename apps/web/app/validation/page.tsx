"use client";
import {useState} from "react";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {
  api, MaterialSummary, MeasurementRecord, RecommendationResponse, SampleRecord,
  ValidationResultRecord,
} from "@/lib/api";
import {ValidationStateBadge} from "@/components/ValidationStateBadge";
import {MeasurementQualityBadge} from "@/components/MeasurementQualityBadge";
import {OriginBadge} from "@/components/OriginBadge";

export default function ValidationWorkspace(){
  const materials = useQuery({queryKey:["materials"],queryFn:()=>api<MaterialSummary[]>("/materials")});
  const measurements = useQuery({
    queryKey:["measurements"],queryFn:()=>api<MeasurementRecord[]>("/experiments/measurements"),
  });
  const policy = useQuery({
    queryKey:["experiment-policy"],
    queryFn:()=>api<{autonomy_note:string;separation_note:string;implemented_designs:string[];
      not_implemented_designs:string[];integration_note:string}>("/experiments/policy"),
  });

  const [roleId,setRoleId]=useState("");
  const [targetId,setTargetId]=useState("");

  const validation = useQuery({
    queryKey:["validation",roleId,targetId], enabled:!!roleId&&!!targetId,
    queryFn:()=>api<ValidationResultRecord>("/experiments/validation/assess",{method:"POST",
      body:JSON.stringify({role_id:roleId, target_kind:"known_material", target_id:targetId, persist:false})}),
  });
  const recommendations = useQuery({
    queryKey:["recommendations",roleId,targetId], enabled:!!roleId&&!!targetId,
    queryFn:()=>api<RecommendationResponse>("/experiments/recommendations",{method:"POST",
      body:JSON.stringify({role_id:roleId, target_kind:"known_material", target_id:targetId, persist:false})}),
  });
  const samples = useQuery({
    queryKey:["samples"], queryFn:()=>api<SampleRecord[]>("/experiments/samples").catch(()=>[]),
  });

  const result = validation.data;

  return <div className="grid">
    <div className="topline">
      <div>
        <div className="eyebrow">Experimental Validation · Phase 9</div>
        <h1>From recommendation to physical evidence</h1>
        <div className="muted">Candidate → requirement → evidence gap → experiment → sample → measurement → validation state.</div>
      </div>
      <div style={{display:"flex",gap:8}}>
        <Link className="btn btn-secondary" href="/reasoning">Reasoning</Link>
        <Link className="btn btn-secondary" href="/">Projects</Link>
      </div>
    </div>

    {policy.data&&<div className="notice" data-testid="experiment-policy">
      <strong>What this system does and does not do</strong>
      <div className="muted">{policy.data.autonomy_note}</div>
      <div className="muted">{policy.data.separation_note}</div>
      <div className="muted" style={{marginTop:6}}>
        Implemented designs: {policy.data.implemented_designs.join(", ")}. <strong>Not implemented:</strong> {policy.data.not_implemented_designs.join(", ")}.
      </div>
      <div className="muted">{policy.data.integration_note}</div>
    </div>}

    <div className="card card-pad">
      <div className="eyebrow">Select</div>
      <div className="grid grid-2">
        <label className="label">Material role
          <input className="input" placeholder="role id" value={roleId} onChange={e=>setRoleId(e.target.value)}/>
        </label>
        <label className="label">Candidate
          <select className="select" value={targetId} onChange={e=>setTargetId(e.target.value)}>
            <option value="">— select —</option>
            {materials.data?.map(m=><option key={m.id} value={m.id}>{m.display_name}</option>)}
          </select>
        </label>
      </div>
    </div>

    {result&&<>
      <div className="card card-pad">
        <div className="eyebrow">Validation state</div>
        <h2><ValidationStateBadge state={result.validation_state}/></h2>
        <div className="muted">{result.rationale}</div>
        <div className="muted" style={{marginTop:6}}>
          {result.experimentally_supported_requirements.length} requirement(s) experimentally supported ·
          {" "}{result.outstanding_requirements.length} outstanding ·
          {" "}{result.measurement_ids.length} accepted measurement(s)
        </div>
      </div>

      {result.conflicting_experiments.length>0&&<div className="card card-pad">
        <div className="eyebrow">Conflicting experiments</div>
        <h2>Measurements disagree — both are kept</h2>
        {result.conflicting_experiments.map((c,i)=><div key={i} className="notice fail" style={{marginTop:8}}>
          <strong>{c.values.join(" vs ")} {c.unit}</strong>
          <div className="muted">{c.detail}</div>
        </div>)}
      </div>}

      <div className="card">
        <div className="card-pad">
          <div className="eyebrow">Prediction vs simulation vs experiment</div>
          <h2>Compared, never merged</h2>
          <p className="muted">{result.separation_note}</p>
        </div>
        <div className="table-wrap"><table>
          <thead><tr><th>Property</th><th>Requirement status</th><th>Values by origin</th><th>Comparison</th></tr></thead>
          <tbody>{result.per_property_comparisons.map(c=><tr key={c.requirement_id}>
            <td><strong>{c.property_key}</strong></td>
            <td className="muted">{c.requirement_status}</td>
            <td>
              {c.experimental_values.map(v=><div key={v.measurement_id}>
                <OriginBadge origin="experimental"/> {v.value} {v.unit}{v.uncertainty?`±${v.uncertainty}`:""}
                <div className="muted" style={{fontSize:11}}>{v.method}</div>
              </div>)}
              {c.other_origin_values.map((v,i)=><div key={i}>
                <OriginBadge origin={String(v.origin)}/> {String(v.value??"—")} {String(v.unit??"")}
              </div>)}
              {c.experimental_values.length===0&&c.other_origin_values.length===0&&
                <span className="muted">No value of any origin.</span>}
            </td>
            <td className="muted" style={{maxWidth:320}}>
              {c.pairwise_comparisons.map((p,i)=><div key={i}>• [{p.verdict}] {p.detail}</div>)}
              {c.pairwise_comparisons.length===0&&<span>Nothing to compare.</span>}
            </td>
          </tr>)}</tbody>
        </table></div>
      </div>
    </>}

    {recommendations.data&&recommendations.data.recommendations.length>0&&<div className="card">
      <div className="card-pad">
        <div className="eyebrow">Recommended experiments</div>
        <h2>What to test next, and why</h2>
        <p className="muted">
          Priority is a weighted combination of declared factors ({Object.entries(recommendations.data.weights).map(([k,v])=>`${k} ${v}`).join(", ")}).
          It is deliberately not called expected value of information: no such mathematics is implemented.
        </p>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Priority</th><th>Requirement</th><th>Why it matters</th><th>Proposed measurement</th><th>Factors</th></tr></thead>
        <tbody>{recommendations.data.recommendations.map(r=><tr key={r.requirement_id}>
          <td><strong>{r.priority_score.toFixed(3)}</strong></td>
          <td>{r.requirement_display_name}<div className="muted">{r.unresolved_status}</div></td>
          <td className="muted" style={{maxWidth:260}}>{r.why_it_matters}</td>
          <td className="muted" style={{maxWidth:260}}>{r.proposed_measurement}</td>
          <td className="muted" style={{fontSize:11}}>
            {Object.entries(r.priority_factors).map(([k,v])=><div key={k}>{k}: {v}</div>)}
          </td>
        </tr>)}</tbody>
      </table></div>
    </div>}

    <div className="grid grid-2">
      <div className="card">
        <div className="card-pad"><div className="eyebrow">Measurements</div><h2>Admissibility is explicit</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Value</th><th>Quality</th><th>Why</th></tr></thead>
          <tbody>{measurements.data?.map(m=><tr key={m.id}>
            <td><strong>{m.numeric_value} {m.unit}</strong>{m.uncertainty?<span className="muted"> ±{m.uncertainty}</span>:null}
              <div className="muted">{m.method}</div></td>
            <td><MeasurementQualityBadge quality={m.quality}/></td>
            <td className="muted" style={{fontSize:11,maxWidth:280}}>
              {m.quality_reasons.length===0?"Traceable to a specimen, calibrated instrument, convertible unit.":
                m.quality_reasons.map((r,i)=><div key={i}>• {r}</div>)}
            </td>
          </tr>)}</tbody>
        </table></div>
      </div>

      <div className="card">
        <div className="card-pad"><div className="eyebrow">Samples</div><h2>Every measurement traces to a specimen</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Sample</th><th>Provenance</th></tr></thead>
          <tbody>{samples.data?.map(s=><tr key={s.id}>
            <td><strong>{s.sample_code}</strong><div className="muted">{s.sample_kind}{s.batch_reference?` · batch ${s.batch_reference}`:""}</div></td>
            <td>{s.provenance_complete
              ? <span className="badge">COMPLETE</span>
              : <><span className="badge">INCOMPLETE</span>
                  {s.provenance_gaps.map((g,i)=><div key={i} className="muted" style={{fontSize:11}}>• {g}</div>)}</>}</td>
          </tr>)}</tbody>
        </table></div>
      </div>
    </div>
  </div>;
}
