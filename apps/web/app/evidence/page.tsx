"use client";

import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {api, MeasurementRecord, SampleRecord} from "@/lib/api";

type Snapshot={id:string;provider:string;provider_name?:string;dataset_key:string;record_count:number;retrieved_at:string;content_checksum:string;is_reproducible:boolean;provider_version?:string};
type Provider={key:string;name:string;configured:boolean;requires_api_key:boolean;server_side_only:boolean;note?:string};

function qualityClass(q:string){const v=q.toLowerCase();return v.includes("admiss")||v.includes("accept")||v.includes("high")?"pass":v.includes("reject")||v.includes("invalid")?"fail":"unknown"}
function when(v?:string){if(!v)return "—";const d=new Date(v);return Number.isNaN(d.getTime())?v:d.toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"})}

export default function EvidenceWorkspace(){
  const measurements=useQuery({queryKey:["evidence-measurements"],queryFn:()=>api<MeasurementRecord[]>("/experiments/measurements").catch(()=>[])});
  const samples=useQuery({queryKey:["evidence-samples"],queryFn:()=>api<SampleRecord[]>("/experiments/samples").catch(()=>[])});
  const snapshots=useQuery({queryKey:["evidence-snapshots"],queryFn:()=>api<Snapshot[]>("/external-data/snapshots?limit=50").catch(()=>[])});
  const providers=useQuery({queryKey:["evidence-providers"],queryFn:()=>api<Provider[]>("/external-data/providers").catch(()=>[])});
  const accepted=(measurements.data??[]).filter(m=>qualityClass(m.quality)==="pass").length;
  const incomplete=(samples.data??[]).filter(s=>!s.provenance_complete).length;
  const configured=(providers.data??[]).filter(p=>p.configured).length;
  const originCounts=(measurements.data??[]).reduce<Record<string,number>>((a,m)=>{a[m.scientific_origin||"experimental"]=(a[m.scientific_origin||"experimental"]??0)+1;return a},{});

  return <div className="workspace-page evidence-workspace">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Evidence Registry</span><h1>Every decision should be traceable to evidence.</h1><p>Keep experimental, computational, literature, and provider records separate—then show exactly which source governed a requirement.</p></div>
      <div className="hero-actions"><Link className="btn btn-secondary" href="/data-sources">Manage data sources</Link><Link className="btn" href="/validation">Physical validation lab</Link></div>
    </div>

    <section className="command-kpis">
      <article><span className="metric-icon green">✓</span><div><small>Accepted measurements</small><strong>{accepted}</strong><em>Admissible experimental evidence</em></div></article>
      <article><span className="metric-icon cyan">◇</span><div><small>Tracked specimens</small><strong>{samples.data?.length??0}</strong><em>{incomplete} provenance gap{incomplete===1?"":"s"}</em></div></article>
      <article><span className="metric-icon violet">▦</span><div><small>External snapshots</small><strong>{snapshots.data?.length??0}</strong><em>Content-addressed datasets</em></div></article>
      <article><span className="metric-icon blue">↗</span><div><small>Configured providers</small><strong>{configured}</strong><em>{providers.data?.length??0} registered connectors</em></div></article>
    </section>

    <section className="evidence-flow command-panel">
      <div className="panel-title-row"><div><span className="panel-kicker">Scientific provenance</span><h2>Evidence pipeline</h2><p>Data stays typed by origin all the way to the decision engine.</p></div><Link href="/validation">Inspect validation →</Link></div>
      <div className="flow-track">
        <div><span className="flow-icon">1</span><strong>Acquire</strong><small>Provider, literature, experiment</small></div><i>→</i>
        <div><span className="flow-icon">2</span><strong>Normalize</strong><small>Identity, units, conditions</small></div><i>→</i>
        <div><span className="flow-icon">3</span><strong>Qualify</strong><small>Quality + provenance checks</small></div><i>→</i>
        <div className="active"><span className="flow-icon">4</span><strong>Evaluate</strong><small>Requirement-specific admissibility</small></div><i>→</i>
        <div><span className="flow-icon">5</span><strong>Defend</strong><small>Audit trail + dossier</small></div>
      </div>
    </section>

    <section className="evidence-grid">
      <div className="command-panel evidence-table-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Experimental evidence</span><h2>Recent measurements</h2></div><span className="count-chip">{measurements.data?.length??0}</span></div>
        <div className="modern-table">
          <div className="modern-table-head evidence-cols"><span>Measurement</span><span>Origin</span><span>Quality</span><span>Traceability</span></div>
          {(measurements.data??[]).slice(0,10).map(m=><div className="modern-table-row evidence-cols" key={m.id}>
            <span><strong>{m.canonical_value??m.numeric_value??"—"} {m.canonical_unit??m.unit??""}</strong><small>{m.method??"Recorded measurement"} · replicate {m.replicate_index}</small></span>
            <span><em className="origin-pill">{(m.scientific_origin||"experimental").replaceAll("_"," ")}</em><small>{when(m.measured_at??m.created_at)}</small></span>
            <span><b className={`status-pill ${qualityClass(m.quality)}`}>{m.quality.replaceAll("_"," ")}</b>{m.uncertainty!==undefined&&<small>± {m.uncertainty}</small>}</span>
            <span><strong>{m.sample_id?"Sample linked":"No sample"}</strong><small>{m.instrument_id?"Instrument linked":"Instrument not recorded"}</small></span>
          </div>)}
          {measurements.isLoading&&<div className="panel-empty">Loading evidence…</div>}
          {!measurements.isLoading&&(measurements.data?.length??0)===0&&<div className="panel-empty">No experimental measurements are recorded yet. Use Physical Validation to capture traceable results.</div>}
        </div>
      </div>

      <aside className="command-panel origin-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Origin separation</span><h2>Evidence mix</h2></div></div>
        <div className="origin-donut"><div><strong>{measurements.data?.length??0}</strong><small>MEASUREMENTS</small></div></div>
        <div className="origin-list">
          {Object.entries(originCounts).map(([k,v],i)=><div key={k}><span><i className={`origin-dot o${i%4}`}/>{k.replaceAll("_"," ")}</span><div><b style={{width:`${Math.max(6,Math.round(v/Math.max(1,measurements.data?.length??1)*100))}%`}}/></div><strong>{v}</strong></div>)}
          {Object.keys(originCounts).length===0&&<div className="panel-empty small">Origin distribution appears after measurements are recorded.</div>}
        </div>
        <div className="evidence-rule"><span>!</span><p><strong>Never merge origins silently.</strong> Simulation, prediction, provider data, and physical measurement remain distinguishable in every decision.</p></div>
      </aside>
    </section>

    <section className="workspace-split evidence-bottom">
      <div className="command-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Specimen chain</span><h2>Physical sample provenance</h2></div><Link href="/validation">Open lab →</Link></div>
        <div className="sample-grid">{(samples.data??[]).slice(0,8).map(s=><article key={s.id}><span className="sample-icon">⬡</span><div><strong>{s.display_name||s.sample_code}</strong><small>{s.sample_kind}{s.batch_reference?` · batch ${s.batch_reference}`:""}</small></div><b className={`status-pill ${s.provenance_complete?"pass":"unknown"}`}>{s.provenance_complete?"COMPLETE":"GAPS"}</b></article>)}{!samples.isLoading&&(samples.data?.length??0)===0&&<div className="panel-empty">No specimens have been registered yet.</div>}</div>
      </div>
      <div className="command-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">External evidence</span><h2>Governed snapshots</h2></div><Link href="/data-sources">Ingest data →</Link></div>
        <div className="snapshot-list">{(snapshots.data??[]).slice(0,6).map(s=><article key={s.id}><span className="snapshot-provider">{(s.provider_name||s.provider).slice(0,2).toUpperCase()}</span><div><strong>{s.dataset_key}</strong><small>{s.provider_name||s.provider} · {s.record_count} records · {when(s.retrieved_at)}</small></div><b className={`status-pill ${s.is_reproducible?"pass":"unknown"}`}>{s.is_reproducible?"PINNED":"TIMESTAMPED"}</b></article>)}{!snapshots.isLoading&&(snapshots.data?.length??0)===0&&<div className="panel-empty">No governed external snapshots yet.</div>}</div>
      </div>
    </section>
  </div>;
}
