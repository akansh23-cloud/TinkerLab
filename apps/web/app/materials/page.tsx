"use client";
import Link from "next/link";
import {useMemo,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {api,ExplorerMaterial} from "@/lib/api";

const families=["","polymer","alloy","composite","ceramic","crystalline_inorganic","coating","adhesive","unknown"];
function familyName(v:string){return v.replaceAll("_"," ")}
function atomLabel(m:ExplorerMaterial){const n=m.display_name.replace(/[^A-Za-z0-9]/g,"");return (n.match(/[A-Z][a-z]?/g)?.slice(0,2).join("")||n.slice(0,2)||"M").slice(0,4)}

export default function MaterialsExplorer(){
  const [q,setQ]=useState("");const [family,setFamily]=useState("");
  const path=useMemo(()=>`/material-explorer?q=${encodeURIComponent(q)}${family?`&family=${encodeURIComponent(family)}`:""}`,[q,family]);
  const result=useQuery({queryKey:["material-explorer",q,family],queryFn:()=>api<ExplorerMaterial[]>(path)});
  const materials=result.data??[];
  const totalObs=materials.reduce((n,m)=>n+m.observation_count,0);const conflicts=materials.reduce((n,m)=>n+m.conflict_count,0);
  const evidenceFamilies=new Set(materials.flatMap(m=>m.evidence_types)).size;
  return <div className="workspace-page materials-workspace">
    <div className="workspace-hero compact"><div><span className="workspace-kicker">Materials Intelligence</span><h1>Explore materials as evidence-bearing identities.</h1><p>Search canonical material records, inspect coverage and conflicts, and move promising candidates into a replacement mission.</p></div><div className="hero-actions"><Link className="btn btn-secondary" href="/imports">Import data</Link><Link className="btn btn-secondary" href="/explore">Property space</Link><Link className="btn" href="/materials/new">+ Record material</Link></div></div>

    <section className="command-kpis"><article><span className="metric-icon blue">⬡</span><div><small>Visible materials</small><strong>{materials.length}</strong><em>Current filter</em></div></article><article><span className="metric-icon cyan">▦</span><div><small>Observations</small><strong>{totalObs}</strong><em>Across result set</em></div></article><article><span className="metric-icon violet">◇</span><div><small>Evidence types</small><strong>{evidenceFamilies}</strong><em>Provenance categories</em></div></article><article><span className={`metric-icon ${conflicts?"amber":"green"}`}>!</span><div><small>Conflicts</small><strong>{conflicts}</strong><em>{conflicts?"Need explicit resolution":"No conflicts in result"}</em></div></article></section>

    <section className="materials-browser command-panel"><div className="materials-toolbar"><label className="material-search"><span>⌕</span><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search material name or canonical identifier…"/></label><label className="family-filter"><span>Family</span><select value={family} onChange={e=>setFamily(e.target.value)}>{families.map(f=><option key={f} value={f}>{f?familyName(f):"All material families"}</option>)}</select></label><span className="result-count">{materials.length} result{materials.length===1?"":"s"}</span></div>
      <div className="material-card-grid">{materials.slice(0,12).map((m,index)=><Link href={`/materials/${m.id}`} className="material-intel-card" key={m.id}><div className={`material-structure s${index%4}`}><span className="atom-core">{atomLabel(m)}</span><i className="bond b1"/><i className="bond b2"/><i className="bond b3"/><i className="atom a1"/><i className="atom a2"/><i className="atom a3"/><i className="atom a4"/></div><div className="material-card-copy"><span className="material-family">{familyName(m.material_family)}</span><h3>{m.display_name}</h3><p>{m.canonical_name}</p><div className="material-card-stats"><span><small>Evidence</small><strong>{m.observation_count}</strong></span><span><small>Origins</small><strong>{m.evidence_types.length}</strong></span><span><small>Conflicts</small><strong className={m.conflict_count?"warn":"good"}>{m.conflict_count}</strong></span></div><div className="material-identifiers">{m.identifiers.slice(0,2).map(i=><em key={`${i.namespace}:${i.value}`}>{i.namespace}: {i.value}</em>)}{m.identifiers.length===0&&<em>No external identifier</em>}</div></div><div className="material-card-foot"><span className={`status-pill ${m.conflict_count?"unknown":"pass"}`}>{m.conflict_count?"REVIEW CONFLICT":"EVIDENCE READY"}</span><b>Inspect →</b></div></Link>)}{result.isLoading&&<div className="panel-empty large">Loading material graph…</div>}{!result.isLoading&&materials.length===0&&<div className="panel-empty large"><h3>No materials match this filter.</h3><p>Record a material, import a dataset, or install the reference library from Mission Control.</p><Link className="btn" href="/materials/new">Record material</Link></div>}</div>
    </section>

    <section className="command-panel material-provenance-bar"><div><span className="principle-icon">◇</span><div><span className="panel-kicker">Identity discipline</span><h2>Same name does not mean same scientific state.</h2><p>TinkerLab keeps canonical identity, state, evidence origin, conditions, and conflicting observations explicit before a value enters a decision.</p></div></div><Link className="btn btn-secondary" href="/evidence">Inspect evidence registry</Link></section>
  </div>;
}
