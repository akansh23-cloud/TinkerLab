"use client";
import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, Observation } from "@/lib/api";

type Provenance={observation_id:string;property_key:string;chain:Array<{stage:string;id?:string;provider?:string;external_record_id?:string;raw_checksum?:string;normalized_checksum?:string;parser_version?:string;evidence_type?:string;status?:string;title?:string;condition_set_id?:string;curator_preferred?:boolean}>};
export default function ObservationInspector({params}:{params:Promise<{id:string}>}){
  const {id}=use(params);
  const obs=useQuery({queryKey:["observation",id],queryFn:()=>api<Observation>(`/observations/${id}`)});
  const provenance=useQuery({queryKey:["provenance",id],queryFn:()=>api<Provenance>(`/observations/${id}/provenance`)});
  if(obs.isLoading)return <div className="empty">Loading observation…</div>;
  if(obs.error||!obs.data)return <div className="empty">Observation unavailable: {(obs.error as Error)?.message}</div>;
  const o=obs.data; const c=o.condition_set;
  return <>
    <div className="topline"><div><div className="eyebrow">Observation inspector</div><h1>{o.property_definition.display_name}</h1><div className="muted">Observation <code>{o.id}</code></div></div><span className={`badge ${o.status==="active"?"pass":"unknown"}`}>{o.status}</span></div>
    <div className="grid grid-2" style={{marginBottom:18}}><div className="card card-pad"><h2>Reported value</h2><p style={{fontSize:28,fontWeight:750}}>{o.value_type==="boolean"?String(o.boolean_value):`${o.numeric_value} ${o.unit??""}`}</p><div className="kicker">Canonical property unit</div><p>{o.property_definition.canonical_unit??"Boolean / not applicable"}</p><div className="kicker">Uncertainty</div><p>{o.uncertainty!==undefined?o.uncertainty:o.uncertainty_stddev!==undefined?`σ ${o.uncertainty_stddev}`:"Not reported"}</p></div><div className="card card-pad"><h2>Scientific context</h2><div className="grid grid-2" style={{marginTop:14}}><div><span className="kicker">Temperature</span><p>{c?.temperature_value!==undefined?`${c.temperature_value} ${c.temperature_unit}`:"Not reported"}</p></div><div><span className="kicker">Pressure</span><p>{c?.pressure_value!==undefined?`${c.pressure_value} ${c.pressure_unit}`:"Not reported"}</p></div><div><span className="kicker">Humidity</span><p>{c?.humidity_percent!==undefined?`${c.humidity_percent}%`:"Not reported"}</p></div><div><span className="kicker">Material state</span><p>{c?.material_state??"Not reported"}</p></div></div></div></div>
    <div className="card card-pad" style={{marginBottom:18}}><h2>Evidence</h2><div style={{display:"flex",gap:8,margin:"12px 0"}}><span className="badge">{o.evidence.evidence_type}</span><span className="badge">{o.evidence.status}</span>{o.curator_preferred&&<span className="badge pass">curator preferred</span>}</div><h3>{o.evidence.title}</h3><p className="muted">{o.evidence.description}</p><div className="grid grid-2"><div><span className="kicker">Method</span><p>{o.method??o.evidence.method??"Not specified"}</p></div><div><span className="kicker">Provider</span><p>{o.evidence.provider?.display_name??"Direct / legacy evidence"}</p></div></div></div>
    <div className="card"><div className="card-pad"><h2>Provenance chain</h2><p className="muted">Provider record → normalization/import → evidence → observation. Checksums identify the exact imported snapshot.</p></div>{provenance.data?.chain.map((step,i)=><div className="card-pad" style={{borderTop:"1px solid var(--line)"}} key={`${step.stage}-${i}`}><div style={{display:"flex",justifyContent:"space-between"}}><strong>{i+1}. {step.stage}</strong>{step.status&&<span className="badge">{step.status}</span>}</div>{step.provider&&<p>{step.provider} · external record {step.external_record_id}</p>}{step.title&&<p>{step.title}</p>}{step.parser_version&&<div><span className="kicker">Parser</span><p><code>{step.parser_version}</code></p></div>}{step.raw_checksum&&<><span className="kicker">Raw SHA-256</span><p><code>{step.raw_checksum}</code></p><span className="kicker">Normalized SHA-256</span><p><code>{step.normalized_checksum}</code></p></>}</div>)}</div>
    <p style={{marginTop:18}}><Link className="btn btn-secondary" href="/materials">Back to materials explorer</Link></p>
  </>;
}
