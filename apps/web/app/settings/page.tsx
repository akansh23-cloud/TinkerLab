"use client";

import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {api, API} from "@/lib/api";

type Deployment={database_reachable:boolean;schema_ready:boolean;bootstrap_required:boolean;alembic_version?:string|null;material_count?:number;reference_library_ready?:boolean;hint?:string};
type Diagnostics={phase?:string;database?:{url_configured?:boolean;dialect?:string;driver?:string;pool?:string};environment_present?:Record<string,boolean>;python_version?:string;backend_root_exists?:boolean};
type Provider={key:string;name:string;configured:boolean;requires_api_key:boolean;server_side_only:boolean;note?:string;api_key_environment?:string};

export default function SettingsWorkspace(){
  const deployment=useQuery({queryKey:["settings-deployment"],queryFn:()=>api<Deployment>("/deployment/status"),retry:1});
  const diagnostics=useQuery({queryKey:["settings-diagnostics"],queryFn:()=>api<Diagnostics>("/deployment/diagnostics"),retry:1});
  const providers=useQuery({queryKey:["settings-providers"],queryFn:()=>api<Provider[]>("/external-data/providers").catch(()=>[])});
  const ready=deployment.data?.database_reachable&&deployment.data?.schema_ready&&!deployment.data?.bootstrap_required;

  return <div className="workspace-page settings-workspace">
    <div className="workspace-hero compact">
      <div><span className="workspace-kicker">Platform Settings</span><h1>Runtime, integrations, and scientific boundaries.</h1><p>Keep deployment health and external evidence providers visible without exposing secret values to the browser.</p></div>
      <div className="hero-actions"><Link className="btn btn-secondary" href="/data-sources">External data sources</Link><a className="btn" href={`${API}/deployment/diagnostics`} target="_blank" rel="noreferrer">Open diagnostics</a></div>
    </div>

    <section className="command-kpis">
      <article><span className={`metric-icon ${deployment.data?.database_reachable?"green":"amber"}`}>●</span><div><small>Database</small><strong>{deployment.data?.database_reachable?"ONLINE":"CHECK"}</strong><em>{diagnostics.data?.database?.driver??"driver unknown"}</em></div></article>
      <article><span className={`metric-icon ${deployment.data?.schema_ready?"green":"amber"}`}>▦</span><div><small>Schema</small><strong>{deployment.data?.schema_ready?"READY":"PENDING"}</strong><em>{deployment.data?.alembic_version??"version unknown"}</em></div></article>
      <article><span className={`metric-icon ${deployment.data?.reference_library_ready?"green":"amber"}`}>◇</span><div><small>Reference library</small><strong>{deployment.data?.reference_library_ready?"READY":"CHECK"}</strong><em>{deployment.data?.material_count??0} material records</em></div></article>
      <article><span className={`metric-icon ${ready?"green":"amber"}`}>✓</span><div><small>Workspace state</small><strong>{ready?"READY":"ATTENTION"}</strong><em>{diagnostics.data?.phase??"runtime"}</em></div></article>
    </section>

    <section className="settings-grid">
      <div className="command-panel runtime-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Production runtime</span><h2>Vercel + FastAPI + Neon</h2></div><span className={`runtime-state ${ready?"ready":"checking"}`}><i/>{ready?"HEALTHY":"CHECK"}</span></div>
        <div className="runtime-map"><div><span className="runtime-node ui">UI</span><strong>Next.js</strong><small>Application shell + labs</small></div><i>→</i><div><span className="runtime-node api">API</span><strong>FastAPI</strong><small>Same-origin /api</small></div><i>→</i><div><span className="runtime-node db">DB</span><strong>Neon PostgreSQL</strong><small>{diagnostics.data?.database?.driver??"psycopg"}</small></div></div>
        <div className="runtime-detail-grid"><div><small>API base</small><code>{API}</code></div><div><small>Python</small><strong>{diagnostics.data?.python_version??"—"}</strong></div><div><small>Database dialect</small><strong>{diagnostics.data?.database?.dialect??"—"}</strong></div><div><small>Pool strategy</small><strong>{diagnostics.data?.database?.pool??"serverless"}</strong></div></div>
        {(deployment.error||diagnostics.error)&&<div className="evidence-rule danger"><span>!</span><p><strong>Runtime check failed.</strong> {String((deployment.error||diagnostics.error) as Error)}</p></div>}
      </div>

      <div className="command-panel scientific-policy-panel">
        <div className="panel-title-row"><div><span className="panel-kicker">Scientific policy</span><h2>Deterministic by default</h2></div></div>
        <div className="policy-list"><article><span>✓</span><div><strong>No generative AI in the decision loop</strong><p>PASS / FAIL / UNKNOWN and ADVANCE / REJECT / HOLD come from stored evidence and explicit rules.</p></div></article><article><span>✓</span><div><strong>Unknown remains unknown</strong><p>Missing evidence is never silently treated as failure or success.</p></div></article><article><span>✓</span><div><strong>Origins remain separate</strong><p>Experimental, simulation, prediction, and provider records remain traceable.</p></div></article><article><span>✓</span><div><strong>Reports are reproducible</strong><p>Dossiers capture checksums and methodology versions instead of free-form generated claims.</p></div></article></div>
      </div>
    </section>

    <section className="command-panel integrations-panel">
      <div className="panel-title-row"><div><span className="panel-kicker">Integrations</span><h2>External scientific data providers</h2><p>Credentials stay server-side. The UI only shows configuration state.</p></div><Link href="/data-sources">Configure ingestion →</Link></div>
      <div className="integration-grid">{(providers.data??[]).map(p=><article key={p.key} className={p.configured?"configured":"unconfigured"}><span className="integration-logo">{p.name.slice(0,2).toUpperCase()}</span><div><strong>{p.name}</strong><small>{p.note??(p.requires_api_key?"API-backed provider":"No credential required")}</small>{p.api_key_environment&&<code>{p.api_key_environment}</code>}</div><b className={`status-pill ${p.configured?"pass":"unknown"}`}>{p.configured?"CONNECTED":"NOT CONFIGURED"}</b></article>)}{providers.isLoading&&<div className="panel-empty">Checking providers…</div>}</div>
    </section>

    <section className="workspace-split settings-bottom">
      <div className="command-panel"><div className="panel-title-row"><div><span className="panel-kicker">Environment visibility</span><h2>Required variables</h2></div></div><div className="env-list">{Object.entries(diagnostics.data?.environment_present??{}).map(([k,v])=><div key={k}><code>{k}</code><b className={`status-pill ${v?"pass":"unknown"}`}>{v?"PRESENT":"MISSING"}</b></div>)}{Object.keys(diagnostics.data?.environment_present??{}).length===0&&<div className="panel-empty">Environment-presence diagnostics are not available.</div>}</div></div>
      <div className="command-panel"><div className="panel-title-row"><div><span className="panel-kicker">Deployment contract</span><h2>Current production shape</h2></div></div><div className="contract-list"><div><span>Root directory</span><code>apps/web</code></div><div><span>Framework</span><strong>Next.js</strong></div><div><span>Python API</span><code>/api/*</code></div><div><span>Database</span><strong>Neon PostgreSQL</strong></div><div><span>AI dependency</span><strong>None</strong></div></div></div>
    </section>
  </div>;
}
