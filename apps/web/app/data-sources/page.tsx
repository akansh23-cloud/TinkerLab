"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Provider = {
  key:string; name:string; requires_api_key:boolean; configured:boolean;
  note?:string; server_side_only?:boolean; api_key_environment?:string; base_url?:string;
  stored_licence?:{license_identifier?:string;commercial_use_permitted?:boolean;redistribution_permitted?:boolean;license_reviewed_by?:string}|null;
};
type Snapshot = {
  id:string;provider?:string;provider_name?:string;dataset_key:string;provider_version?:string;record_count:number;
  retrieved_at:string;content_checksum:string;is_reproducible:boolean;reproducibility_note?:string;
  metadata:Record<string,unknown>;
};
type IngestResult = {
  dataset_snapshot_id:string;provider:string;provider_version?:string;is_reproducible:boolean;record_count:number;
  ingested:number;already_ingested:number;observations:number;industrial_evidence:number;attribution_text?:string;
};
type MethodProfile = {
  id:string;key:string;display_name:string;method_family:string;functional?:string;nominal_temperature_k?:number;
  known_property_bias:Record<string,unknown>;applicability_note?:string;
};

const DEFAULT_QUERIES:Record<string,Record<string,unknown>> = {
  materials_project: {formula:"SiC", max_records:100},
  pubchem: {namespace:"name", identifier:"silicon carbide"},
  epa_comptox: {mode:"by_dtxsid", dtxsid:"REPLACE_WITH_DTXSID"},
  optimade: {filter:'elements HAS "Si"', page_limit:50},
};

export default function DataSourcesPage(){
  const qc=useQueryClient();
  const [provider,setProvider]=useState("materials_project");
  const [datasetKey,setDatasetKey]=useState("external-materials-search");
  const [queryText,setQueryText]=useState(JSON.stringify(DEFAULT_QUERIES.materials_project,null,2));
  const [optimadeBase,setOptimadeBase]=useState("");
  const [optimadeProvider,setOptimadeProvider]=useState("mp");
  const [commercial,setCommercial]=useState(true);

  const providers=useQuery({queryKey:["external-providers"],queryFn:()=>api<Provider[]>("/external-data/providers")});
  const snapshots=useQuery({queryKey:["external-snapshots"],queryFn:()=>api<Snapshot[]>("/external-data/snapshots?limit=50")});
  const methods=useQuery({queryKey:["external-methods"],queryFn:()=>api<MethodProfile[]>("/external-data/methods")});
  const selected=useMemo(()=>providers.data?.find(p=>p.key===provider),[providers.data,provider]);

  const ingest=useMutation({
    mutationFn:async()=>{
      let query:Record<string,unknown>;
      try{query=JSON.parse(queryText);}catch{throw new Error("Query must be valid JSON");}
      return api<IngestResult>("/external-data/ingest",{method:"POST",body:JSON.stringify({
        provider,dataset_key:datasetKey,query,commercial_context:commercial,
        ...(provider==="optimade"?{optimade_base_url:optimadeBase,optimade_provider_id:optimadeProvider}:{}),
      })});
    },
    onSuccess:()=>qc.invalidateQueries({queryKey:["external-snapshots"]}),
  });

  const choose=(key:string)=>{setProvider(key);setQueryText(JSON.stringify(DEFAULT_QUERIES[key]??{},null,2));ingest.reset();};

  return <>
    <div className="topline"><div><div className="eyebrow">Phase 12.2 · governed external evidence</div><h1>External data sources</h1><div className="muted">Ingest provider data through licence gates, content-addressed snapshots, conservative identity resolution and explicit method provenance.</div></div></div>
    <div className="notice" style={{marginBottom:18}}>API keys remain server-side. Unreviewed or non-redistributable evidence cannot silently become an exportable dossier. A provider API version is never treated as a dataset release.</div>
    <div className="card card-pad" style={{marginBottom:18}}>
      <div className="eyebrow">Demo-friendly real data path</div>
      <h2>Pull real computational records, then keep physical validation separate</h2>
      <p className="muted">
        For the flagship demo, use Materials Project to show that TinkerLab can ingest real, provenance-preserved
        computational records. The current connector maps band gap, formation energy, energy above hull, density,
        bulk/shear modulus and magnetization when available. It does not pretend those values are physical tests.
      </p>
      <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:12}}>
        <button className="btn btn-secondary" onClick={()=>{setProvider("materials_project");setDatasetKey("mp-sic-screen");setQueryText(JSON.stringify({formula:"SiC",max_records:100},null,2));}}>SiC records</button>
        <button className="btn btn-secondary" onClick={()=>{setProvider("materials_project");setDatasetKey("mp-gan-screen");setQueryText(JSON.stringify({formula:"GaN",max_records:100},null,2));}}>GaN records</button>
        <button className="btn btn-secondary" onClick={()=>{setProvider("materials_project");setDatasetKey("mp-aln-screen");setQueryText(JSON.stringify({formula:"AlN",max_records:100},null,2));}}>AlN records</button>
        <button className="btn btn-secondary" onClick={()=>{setProvider("materials_project");setDatasetKey("mp-carbon-screen");setQueryText(JSON.stringify({formula:"C",band_gap_min:2.0,max_records:100},null,2));}}>Wide-gap carbon records</button>
      </div>
      <div className="notice" style={{marginTop:12}}>
        <strong>Key demo point:</strong> database screening can nominate candidates, but a missing breakdown-field or
        application-specific thermal result remains an evidence gap. That is where TinkerLab proposes the next test
        instead of inventing a pass.
      </div>
    </div>
    <div className="grid grid-2">
      <div className="card card-pad">
        <h2>Run ingestion</h2>
        <div className="grid" style={{marginTop:16}}>
          <label className="label">Provider<select className="select" value={provider} onChange={e=>choose(e.target.value)}>{(providers.data??[]).map(p=><option key={p.key} value={p.key}>{p.name}</option>)}</select></label>
          {selected&&<div style={{display:"flex",gap:8,flexWrap:"wrap"}}><span className={`badge ${selected.configured?"pass":"fail"}`}>{selected.configured?"CONFIGURED":"NOT CONFIGURED"}</span>{selected.stored_licence?.license_identifier&&<span className="badge">{selected.stored_licence.license_identifier}</span>}</div>}
          {selected?.note&&<div className="muted">{selected.note}</div>}
          {selected?.requires_api_key && selected.server_side_only && <div className="muted">
            API credential: <code>{selected.api_key_environment ?? "server environment"}</code> · server-side only{selected.configured ? " · ready" : " · add it to the API deployment environment"}.
          </div>}
          <label className="label">Dataset key<input className="input" value={datasetKey} onChange={e=>setDatasetKey(e.target.value)} /></label>
          {provider==="optimade"&&<><label className="label">OPTIMADE HTTPS base URL<input className="input" placeholder="https://provider.example" value={optimadeBase} onChange={e=>setOptimadeBase(e.target.value)}/></label><label className="label">Provider prefix<input className="input" value={optimadeProvider} onChange={e=>setOptimadeProvider(e.target.value)}/></label></>}
          <label className="label">Provider query<textarea className="textarea" rows={11} value={queryText} onChange={e=>setQueryText(e.target.value)}/></label>
          <label style={{display:"flex",gap:8,alignItems:"center",fontSize:13}}><input type="checkbox" checked={commercial} onChange={e=>setCommercial(e.target.checked)}/> Commercial-use licence gate</label>
          <button className="btn" disabled={!datasetKey||ingest.isPending||selected?.configured===false} onClick={()=>ingest.mutate()}>{ingest.isPending?"Ingesting…":"Ingest governed snapshot"}</button>
          {ingest.error&&<div className="notice">{(ingest.error as Error).message}</div>}
          {ingest.data&&<div className="card card-pad"><div style={{display:"flex",gap:8,flexWrap:"wrap"}}><span className="badge pass">{ingest.data.ingested} ingested</span><span className="badge">{ingest.data.observations} observations</span><span className={`badge ${ingest.data.is_reproducible?"pass":"unknown"}`}>{ingest.data.is_reproducible?"PINNED":"TIME-STAMPED"}</span></div><div className="muted" style={{marginTop:10}}>Snapshot <code>{ingest.data.dataset_snapshot_id}</code></div></div>}
        </div>
      </div>
      <div className="card card-pad">
        <h2>Snapshot history</h2>
        {snapshots.isLoading&&<div className="empty">Loading snapshots…</div>}
        {snapshots.error&&<div className="notice">{(snapshots.error as Error).message}</div>}
        {!snapshots.isLoading&&(snapshots.data?.length??0)===0&&<div className="empty">No external snapshots in this organisation yet.</div>}
        <div className="grid" style={{marginTop:12}}>{(snapshots.data??[]).map(s=><div className="card card-pad" key={s.id}><div style={{display:"flex",justifyContent:"space-between",gap:12}}><div><strong>{s.dataset_key}</strong><div className="muted">{s.provider_name??s.provider} · {s.record_count} records</div></div><span className={`badge ${s.is_reproducible?"pass":"unknown"}`}>{s.is_reproducible?"REPRODUCIBLE":"UNPINNED"}</span></div><div className="muted" style={{marginTop:8}}>Dataset version: {s.provider_version??"not exposed"}</div><div className="muted">SHA-256: <code>{s.content_checksum.slice(0,16)}…</code></div>{s.reproducibility_note&&<div className="notice" style={{marginTop:8}}>{s.reproducibility_note}</div>}</div>)}</div>
      </div>
    </div>
    <div className="card card-pad" style={{marginTop:18}}>
      <h2>Computational provenance catalogue</h2>
      <div className="muted" style={{marginTop:6}}>Computed evidence keeps its calculation class explicit. Unknown functional stays unknown; these heuristics generate warnings and are never silent correction factors.</div>
      {methods.error&&<div className="notice" style={{marginTop:12}}>{(methods.error as Error).message}</div>}
      <div className="grid grid-2" style={{marginTop:12}}>{(methods.data??[]).map(m=><div className="card card-pad" key={m.id}><strong>{m.display_name}</strong><div className="muted">{m.method_family}{m.functional?` · ${m.functional}`:""}{m.nominal_temperature_k!==undefined&&m.nominal_temperature_k!==null?` · ${m.nominal_temperature_k} K`:""}</div>{m.applicability_note&&<div className="muted" style={{marginTop:6}}>{m.applicability_note}</div>}</div>)}</div>
    </div>
  </>;
}
