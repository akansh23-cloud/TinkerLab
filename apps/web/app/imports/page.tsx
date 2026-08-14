"use client";
import { ChangeEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

const DEMO_ORG="0b5ec369-282c-57b5-9781-471f818a07c3";
type Preview={payload_checksum:string;format:string;valid:boolean;material_count:number;observation_count:number;warnings:Array<Record<string,unknown>>;errors:Array<Record<string,unknown>>;normalized_preview:Array<Record<string,unknown>>};
type Commit={import_id:string;status:string;idempotent_replay:boolean;payload_checksum:string;summary:Record<string,number>;errors:Array<Record<string,unknown>>};
export default function ImportCenter(){
  const [org,setOrg]=useState(DEMO_ORG); const [format,setFormat]=useState<"json"|"csv">("json"); const [content,setContent]=useState("");
  const preview=useMutation({mutationFn:()=>api<Preview>("/imports/preview",{method:"POST",body:JSON.stringify({organisation_id:org,input_format:format,content,provider_key:"local_import"})})});
  const commit=useMutation({mutationFn:()=>api<Commit>("/imports",{method:"POST",body:JSON.stringify({organisation_id:org,input_format:format,content,provider_key:"local_import"})})});
  const onFile=async(e:ChangeEvent<HTMLInputElement>)=>{const file=e.target.files?.[0];if(!file)return;if(file.size>2_000_000){alert("Import file must be 2 MB or smaller in Phase 2.");return;} const ext=file.name.split(".").pop()?.toLowerCase();setFormat(ext==="csv"?"csv":"json");setContent(await file.text());preview.reset();commit.reset();};
  return <>
    <div className="topline"><div><div className="eyebrow">Controlled ingestion</div><h1>Import center</h1><div className="muted">Preview validation first. Commit only after the normalized record and row errors are visible.</div></div></div>
    <div className="notice" style={{marginBottom:18}}>Imported source records retain raw and normalized SHA-256 checksums, parser version, provider identity, and organisation scope. TinkerLab never executes spreadsheet formulas or imported code.</div>
    <div className="grid grid-2">
      <div className="card card-pad"><h2>Source data</h2><div className="grid" style={{marginTop:16}}><label className="label">Organisation ID<input className="input" value={org} onChange={e=>setOrg(e.target.value)}/></label><label className="label">Format<select className="select" value={format} onChange={e=>setFormat(e.target.value as "json"|"csv")}><option value="json">JSON</option><option value="csv">CSV</option></select></label><label className="label">Choose file<input className="input" type="file" accept=".json,.csv,application/json,text/csv" onChange={onFile}/></label><label className="label">Raw content<textarea className="textarea" rows={16} value={content} onChange={e=>{setContent(e.target.value);preview.reset();commit.reset();}} placeholder='{"materials": [...]}'/></label><div style={{display:"flex",gap:8}}><button className="btn btn-secondary" disabled={!content||preview.isPending} onClick={()=>preview.mutate()}>{preview.isPending?"Validating…":"Dry-run preview"}</button><button className="btn" disabled={!preview.data?.valid||commit.isPending} onClick={()=>commit.mutate()}>{commit.isPending?"Committing…":"Commit validated import"}</button></div></div></div>
      <div className="grid">
        <div className="card card-pad"><h2>Validation</h2>{!preview.data&&!preview.error&&<div className="empty">Run a dry preview to inspect validation and normalization.</div>}{preview.error&&<div className="notice">{(preview.error as Error).message}</div>}{preview.data&&<><div style={{display:"flex",gap:8,margin:"12px 0"}}><span className={`badge ${preview.data.valid?"pass":"fail"}`}>{preview.data.valid?"VALID":"INVALID"}</span><span className="badge">{preview.data.material_count} materials</span><span className="badge">{preview.data.observation_count} observations</span></div>{preview.data.errors.length>0&&<pre className="json">{JSON.stringify(preview.data.errors,null,2)}</pre>}{preview.data.warnings.length>0&&<><div className="kicker">Warnings</div><pre className="json">{JSON.stringify(preview.data.warnings,null,2)}</pre></>}</>}</div>
        {preview.data?.valid&&<div className="card card-pad"><h2>Normalized preview</h2><pre className="json" style={{marginTop:12}}>{JSON.stringify(preview.data.normalized_preview,null,2)}</pre></div>}
        {commit.data&&<div className="card card-pad"><h2>Import result</h2><p><span className="badge pass">{commit.data.status}</span> {commit.data.idempotent_replay&&<span className="badge">idempotent replay</span>}</p><pre className="json">{JSON.stringify(commit.data.summary,null,2)}</pre><div className="muted" style={{marginTop:10}}>Import ID: <code>{commit.data.import_id}</code></div></div>}
      </div>
    </div>
  </>;
}
