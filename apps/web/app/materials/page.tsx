"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ExplorerMaterial } from "@/lib/api";

const families=["","polymer","alloy","composite","ceramic","crystalline_inorganic","coating","adhesive","unknown"];
export default function MaterialsExplorer(){
  const [q,setQ]=useState(""); const [family,setFamily]=useState("");
  const path=useMemo(()=>`/material-explorer?q=${encodeURIComponent(q)}${family?`&family=${encodeURIComponent(family)}`:""}`,[q,family]);
  const result=useQuery({queryKey:["material-explorer",q,family],queryFn:()=>api<ExplorerMaterial[]>(path)});
  return <>
    <div className="topline"><div><div className="eyebrow">Knowledge graph</div><h1>Materials explorer</h1><div className="muted">Search normalized material identities and inspect evidence coverage without collapsing conflicting observations.</div></div><div style={{display:"flex",gap:8}}><Link className="btn" href="/materials/new">Record a material</Link><Link className="btn btn-secondary" href="/explore">Property space</Link><Link className="btn btn-secondary" href="/imports">Import data</Link></div></div>
    <div className="card card-pad" style={{marginBottom:18}}><div className="grid grid-2"><label className="label">Search<input className="input" value={q} onChange={e=>setQ(e.target.value)} placeholder="Name or canonical identifier"/></label><label className="label">Family<select className="select" value={family} onChange={e=>setFamily(e.target.value)}>{families.map(f=><option key={f} value={f}>{f||"All families"}</option>)}</select></label></div></div>
    <div className="card"><div className="table-wrap"><table><thead><tr><th>Material</th><th>Identifiers</th><th>Family</th><th>Evidence coverage</th><th>Conflicts</th><th>Source</th></tr></thead><tbody>
      {result.data?.map(m=><tr key={m.id}><td><Link href={`/materials/${m.id}`}><strong>{m.display_name}</strong></Link><div className="muted">{m.canonical_name}</div></td><td>{m.identifiers.slice(0,2).map(i=><div key={`${i.namespace}:${i.value}`}><span className="badge">{i.namespace}</span> {i.value}</div>)}</td><td>{m.material_family}</td><td>{m.observation_count} observation(s)<div className="muted">{m.evidence_types.join(" · ")||"No evidence"}</div></td><td>{m.conflict_count?<span className="badge fail">{m.conflict_count} conflict{m.conflict_count>1?"s":""}</span>:<span className="badge pass">None detected</span>}</td><td><span className="badge">{m.source_type}</span>{m.is_seed_data&&<div className="muted">demo-only</div>}</td></tr>)}
      {!result.isLoading&&result.data?.length===0&&<tr><td colSpan={6}><div className="empty">No materials match these filters. <Link href="/materials/new"><strong>Record one</strong></Link>, or install the reference library from the dashboard.</div></td></tr>}
    </tbody></table></div>{result.isLoading&&<div className="empty">Loading material graph…</div>}{result.error&&<div className="empty">Unable to load materials: {(result.error as Error).message}</div>}</div>
  </>;
}
