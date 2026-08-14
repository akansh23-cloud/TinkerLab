"use client";
import {useState} from "react";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {
  api, CandidateReasoning, MaterialStateRecord, MaterialSummary, RoleDecomposition,
} from "@/lib/api";
import {RequirementStatusBadge} from "@/components/RequirementStatusBadge";
import {OriginBadge} from "@/components/OriginBadge";

type ApplicationSummary = {
  id: string; key: string; display_name: string; domain?: string; description?: string;
  components: Array<{id: string; key: string; display_name: string}>;
};

export default function ReasoningWorkspace(){
  const applications = useQuery({
    queryKey:["reasoning-applications"],
    queryFn:()=>api<ApplicationSummary[]>("/reasoning/applications"),
  });
  const materials = useQuery({queryKey:["materials"],queryFn:()=>api<MaterialSummary[]>("/materials")});

  const [roleId,setRoleId]=useState<string>("");
  const [candidateId,setCandidateId]=useState<string>("");
  const [openRequirement,setOpenRequirement]=useState<string|null>(null);
  const [stateId,setStateId]=useState<string>("");

  const decomposition = useQuery({
    queryKey:["reasoning-decomposition",roleId], enabled:!!roleId,
    queryFn:()=>api<RoleDecomposition>(`/reasoning/roles/${roleId}/decomposition`),
  });
  const states = useQuery({
    queryKey:["reasoning-states",candidateId], enabled:!!candidateId,
    queryFn:()=>api<MaterialStateRecord[]>(
      `/reasoning/material-states?target_kind=known_material&target_id=${candidateId}`),
  });
  const reasoning = useQuery({
    queryKey:["reasoning-candidate",roleId,candidateId,stateId], enabled:!!roleId&&!!candidateId,
    queryFn:()=>api<CandidateReasoning>("/reasoning/candidate",{method:"POST",body:JSON.stringify({
      role_id:roleId, target_kind:"known_material", target_id:candidateId,
      ...(stateId?{state_id:stateId}:{}), persist:false})}),
  });

  const result = reasoning.data;
  const openDetail = result?.requirement_results.find(r=>r.requirement_id===openRequirement);

  return <div className="grid">
    <div className="topline">
      <div>
        <div className="eyebrow">Replacement Reasoning · Phase 8</div>
        <h1>What must a replacement actually preserve?</h1>
        <div className="muted">Application → component → role → function → requirement. A candidate is judged on what it does here, not on chemical resemblance.</div>
      </div>
      <Link className="btn btn-secondary" href="/">Projects</Link>
    </div>

    <div className="card card-pad">
      <div className="eyebrow">Study setup</div>
      <div className="grid grid-3">
        <label className="label">Application
          <select className="select" value={applications.data?.[0]?.id??""} onChange={()=>{}}>
            {applications.data?.map(a=><option key={a.id} value={a.id}>{a.display_name}</option>)}
          </select>
        </label>
        <label className="label">Material role
          <input className="input" placeholder="role id" value={roleId}
                 onChange={e=>{setRoleId(e.target.value);setOpenRequirement(null);}}/>
          <span className="muted" style={{fontSize:11}}>
            {decomposition.data
              ? `${decomposition.data.role.display_name} in ${decomposition.data.component?.display_name}`
              : "Enter the role identifier for the study."}
          </span>
        </label>
        <label className="label">Candidate material
          <select className="select" value={candidateId} onChange={e=>{setCandidateId(e.target.value);setStateId("");setOpenRequirement(null);}}>
            <option value="">— select —</option>
            {materials.data?.map(m=><option key={m.id} value={m.id}>{m.display_name}</option>)}
          </select>
        </label>
      </div>
      {candidateId&&<div className="notice" style={{marginTop:10}}>
        <strong>Material state</strong>
        <div className="muted">A property belongs to a material in a state. Which state you ask about changes which evidence is admissible, so it is chosen explicitly rather than assumed.</div>
        <select className="select" style={{marginTop:6}} value={stateId}
                onChange={e=>{setStateId(e.target.value);setOpenRequirement(null);}}>
          <option value="">Reference state (default)</option>
          {states.data?.map(s=><option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        {states.data?.length===0&&<div className="muted" style={{marginTop:4}}>
          No material state is recorded for this candidate. Every comparison below will be state-unqualified.
        </div>}
      </div>}
    </div>

    {decomposition.data&&<div className="card">
      <div className="card-pad">
        <div className="eyebrow">Functional decomposition</div>
        <h2>{decomposition.data.role.display_name}</h2>
        <div className="muted">
          {decomposition.data.application?.display_name} → {decomposition.data.component?.display_name} → {decomposition.data.role.display_name}
        </div>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Function</th><th>Criticality</th><th>Requirement</th><th>Test</th><th>Why</th></tr></thead>
        <tbody>{decomposition.data.functions.flatMap(f=>
          f.requirements.map((r,i)=><tr key={r.id}>
            <td>{i===0?<><strong>{f.display_name}</strong><div className="muted">{f.category}</div></>:null}</td>
            <td>{i===0?<span className="badge">{f.criticality}</span>:null}</td>
            <td><strong>{r.display_name}</strong><div className="muted">{r.requirement_kind}</div></td>
            <td className="muted">{r.direction}{r.target_value!=null?` ${r.target_value}`:""}
              {r.target_value_upper!=null?`–${r.target_value_upper}`:""} {r.target_unit??""}</td>
            <td className="muted" style={{maxWidth:280}}>{r.rationale}</td>
          </tr>))}
        </tbody>
      </table></div>
    </div>}

    {result&&<>
      <div className="card card-pad">
        <div className="eyebrow">Candidate assessment</div>
        <h2><RequirementStatusBadge status={result.overall_status}/></h2>
        <div className="muted">
          State: {result.state?result.state.label:"none recorded"}
          {result.state?.structure_identity&&<> · structure identity <code>{result.state.structure_identity.slice(0,14)}…</code></>}
          {result.state?.composition_signature&&<> · composition {result.state.composition_signature}</>}
        </div>
        {result.state_warning&&<div className="notice fail" style={{marginTop:8}}>{result.state_warning}</div>}
        <div className="notice" style={{marginTop:10}}>
          <strong>Evidence origins are kept apart</strong>
          <div className="muted">{result.origin_separation_note}</div>
          <div style={{marginTop:6,display:"flex",gap:6,flexWrap:"wrap"}}>
            {Object.entries(result.origin_breakdown).map(([origin,count])=>
              <span key={origin}><OriginBadge origin={origin}/> ×{count}</span>)}
            {Object.keys(result.origin_breakdown).length===0&&
              <span className="muted">No value of any origin was found for this role&apos;s requirements.</span>}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-pad"><div className="eyebrow">Requirement by requirement</div>
          <h2>Which requirements hold, which fail, which are simply unknown</h2></div>
        <div className="table-wrap"><table>
          <thead><tr><th>Requirement</th><th>Function</th><th>Status</th><th>Governing origin</th><th>Detail</th><th/></tr></thead>
          <tbody>{result.requirement_results.map(r=><tr key={r.requirement_id}>
            <td><strong>{r.display_name}</strong><div className="muted">{r.requirement_kind} · {r.property_key}</div></td>
            <td className="muted">{r.function_display_name}</td>
            <td><RequirementStatusBadge status={r.status}/></td>
            <td>{r.governing_origin?<OriginBadge origin={r.governing_origin}/>:<span className="muted">—</span>}</td>
            <td className="muted" style={{maxWidth:320}}>{r.detail}</td>
            <td><button className="btn btn-secondary" style={{fontSize:11,padding:"2px 8px"}}
                        onClick={()=>setOpenRequirement(openRequirement===r.requirement_id?null:r.requirement_id)}>
              {openRequirement===r.requirement_id?"hide":"values"}</button></td>
          </tr>)}</tbody>
        </table></div>
      </div>

      {openDetail&&<div className="card card-pad">
        <div className="eyebrow">All values considered</div>
        <h2>{openDetail.display_name}</h2>
        {openDetail.origin_note&&<div className="muted">{openDetail.origin_note}</div>}
        <div className="table-wrap" style={{marginTop:8}}><table>
          <thead><tr><th>Origin</th><th>Value</th><th>State match</th><th>Used?</th><th>Detail</th></tr></thead>
          <tbody>{(openDetail.values??[]).map(v=><tr key={v.source_id}>
            <td><OriginBadge origin={v.origin}/></td>
            <td>{v.value!=null?`${v.value} ${v.unit??""}`:"—"}</td>
            <td className="muted">{v.state_match}
              {v.state_reasons.length>0&&<div style={{fontSize:11}}>{v.state_reasons[0]}</div>}</td>
            <td>{v.usable?<span className="badge">used</span>:<span className="badge">not used</span>}</td>
            <td className="muted" style={{maxWidth:300}}>{v.detail}</td>
          </tr>)}</tbody>
        </table></div>
        {(openDetail.values??[]).length===0&&
          <div className="muted">No value of any origin exists. This is an evidence gap, not a failure.</div>}
      </div>}

      <div className="grid grid-2">
        <div className="card card-pad">
          <div className="eyebrow">Evidence gaps</div>
          <h2>{result.evidence_gaps.length===0?"None":"What would need determining"}</h2>
          {result.evidence_gaps.map(g=><div key={g.requirement_id} className="notice" style={{marginTop:8}}>
            <strong>{g.display_name}</strong> <RequirementStatusBadge status={g.status}/>
            <div className="muted">{g.detail}</div>
            <div className="muted"><strong>To resolve:</strong> {g.what_would_resolve_it}</div>
          </div>)}
        </div>

        <div className="card card-pad">
          <div className="eyebrow">Mechanism chains</div>
          <h2>Why the property is the right thing to ask about</h2>
          <div className="muted">{result.mechanism_note}</div>
          {result.mechanism_paths.map((p,i)=><div key={i} className="notice" style={{marginTop:8}}>
            <strong>{p.property_key}</strong>
            <div className="muted">{p.chain.map(n=>n.kind).join(" → ")}</div>
            {p.edges.map(e=><div key={e.edge_id} className="muted" style={{fontSize:11}}>
              • {e.note} <em>(scope: {e.scope??"unscoped"}; confidence {e.confidence??"—"})</em>
            </div>)}
            <div className="muted" style={{fontSize:11}}>
              Weakest link confidence: {p.weakest_confidence??"—"} — a chain is only as supported as its least supported step.
            </div>
          </div>)}
        </div>
      </div>

      {result.assumptions.length>0&&<div className="card card-pad">
        <div className="eyebrow">Assumptions</div>
        <h2>What this assessment took for granted</h2>
        {result.assumptions.map((a,i)=><div key={i} className="muted">• {a}</div>)}
        <div className="muted" style={{marginTop:10,fontSize:11}}>{result.structured_first_note}</div>
      </div>}
    </>}
  </div>;
}
