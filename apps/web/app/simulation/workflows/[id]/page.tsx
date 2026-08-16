"use client";
import {use, useEffect, useState} from "react";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {api, SimulationWorkflowDetail} from "@/lib/api";
import {SimulationWarning} from "@/components/SimulationWarning";
import {ConvergenceBadge} from "@/components/ConvergenceBadge";

type ReplacementProgram={id:string;project_id:string};
type DecisionAction={id:string;candidate_id?:string|null;requirement_key?:string|null;action_type:string;status:string};
type DecisionSync={completed:number;eligible:number;note:string};

export default function SimulationWorkflowPage({params}:{params:Promise<{id:string}>}){
  const {id}=use(params);
  const detail=useQuery({queryKey:["sim-workflow",id],queryFn:()=>api<SimulationWorkflowDetail>(`/simulation/workflows/${id}`)});
  const [decisionSync,setDecisionSync]=useState<DecisionSync|null>(null);
  const [decisionSyncError,setDecisionSyncError]=useState("");
  const [syncing,setSyncing]=useState(false);

  async function closeDecisionActions(){
    const data=detail.data;
    if(!data||syncing||decisionSync)return;
    const {workflow,result,property_estimates}=data;
    if(!workflow.project_id||!workflow.candidate_id){
      setDecisionSync({completed:0,eligible:0,note:"This workflow was not launched with project/candidate context, so no replacement-decision action was changed."});
      return;
    }
    if(!result||result.scientific_status!=="converged"){
      setDecisionSync({completed:0,eligible:0,note:`Simulation scientific status is ${result?.scientific_status??"no_result"}; decision actions remain open until a scientifically converged result exists.`});
      return;
    }
    if(!property_estimates.length){
      setDecisionSync({completed:0,eligible:0,note:"The workflow converged but produced no registered property estimate. No decision action was closed."});
      return;
    }
    setSyncing(true);setDecisionSyncError("");
    try{
      const programs=await api<ReplacementProgram[]>(`/replacement-programs?project_id=${encodeURIComponent(workflow.project_id)}`);
      let eligible=0,completed=0;
      for(const program of programs){
        const actions=await api<DecisionAction[]>(`/replacement-programs/${program.id}/actions?status=open`);
        for(const action of actions){
          if(action.action_type!=="run_simulation"||action.candidate_id!==workflow.candidate_id)continue;
          if(action.requirement_key&&workflow.requested_property_key&&action.requirement_key!==workflow.requested_property_key)continue;
          if(action.requirement_key&&!workflow.requested_property_key)continue;
          eligible+=1;
          await api(`/replacement-programs/${program.id}/actions/${action.id}/transition`,{
            method:"POST",
            body:JSON.stringify({
              transition:"complete",
              result_reference:`simulation_result:${result.id}:${result.result_checksum}`,
              note:`Closed automatically from scientifically converged simulation workflow ${workflow.id}. The result remains simulated evidence and is not a measurement or physical qualification.`,
            }),
          });
          completed+=1;
        }
      }
      setDecisionSync({completed,eligible,note:completed?"Matching candidate-scoped simulation actions were closed with an immutable result ID/checksum reference. Scoped evidence events and reassessment are handled by the replacement-decision backend.":"No open simulation action matched this candidate/property; no decision state was changed."});
    }catch(e){
      setDecisionSyncError(e instanceof Error?e.message:"Simulation converged, but decision-loop synchronization failed.");
    }finally{setSyncing(false)}
  }

  useEffect(()=>{if(detail.data&&!decisionSync&&!decisionSyncError)void closeDecisionActions();},[detail.data,decisionSync,decisionSyncError]);

  if(detail.isLoading) return <div className="empty">Loading simulation workflow…</div>;
  if(detail.error||!detail.data) return <div className="empty">Workflow unavailable: {(detail.error as Error)?.message}</div>;
  const {workflow,steps,jobs,artifacts,result,property_estimates}=detail.data;
  return <div className="grid">
    <div className="topline">
      <div>
        <div className="eyebrow">Simulation Workflow · Phase 6</div>
        <h1>{workflow.workflow_template_key} <span className="badge">{workflow.status}</span></h1>
        <div className="muted">Purpose {workflow.requested_purpose} · fidelity {workflow.requested_fidelity} · target {workflow.target_kind}</div>
      </div>
      <Link className="btn btn-secondary" href="/simulation">Simulation Lab</Link>
    </div>
    <SimulationWarning/>
    {(decisionSync||decisionSyncError||syncing)&&<div className={`notice ${decisionSyncError?"fail":""}`}><strong>Decision-loop integration</strong>{syncing&&<div className="muted">Checking for a matching open simulation action…</div>}{decisionSync&&<div><div>{decisionSync.completed}/{decisionSync.eligible} matching validation action(s) closed.</div><div className="muted">{decisionSync.note}</div></div>}{decisionSyncError&&<div className="muted">The simulation result remains valid and persisted, but its decision action was left open: {decisionSyncError}</div>}</div>}

    <div className="grid grid-2">
      <div className="card card-pad">
        <div className="eyebrow">Scientific result</div>
        <h2><ConvergenceBadge status={result?.scientific_status}/></h2>
        {result?<>
          <div className="muted">Operational status <strong>{result.operational_status}</strong> is recorded separately: a clean exit code is never treated as convergence.</div>
          <div className="muted" style={{marginTop:6}}>parser {result.parser_key} v{result.parser_version} · convergence evaluator v{result.convergence_evaluator_version}</div>
          <div className="muted">result checksum <code>{result.result_checksum.slice(0,20)}…</code></div>
          <div style={{marginTop:8}}><strong>Convergence metrics</strong>
            <pre style={{fontSize:11,whiteSpace:"pre-wrap"}}>{JSON.stringify(result.convergence_metrics,null,1)}</pre></div>
          {result.warnings.length>0&&<div className="notice fail"><strong>Warnings</strong>{result.warnings.map((w,i)=><div key={i} className="muted">• {w}</div>)}</div>}
          <div className="notice" style={{marginTop:8}}><strong>Method limitations</strong>
            {result.method_limitations.map((l,i)=><div key={i} className="muted">• {l}</div>)}</div>
        </>:<div className="muted">No scientific result was produced.</div>}
      </div>
      <div className="card card-pad">
        <div className="eyebrow">Property estimates</div>
        <h2>{property_estimates.length===0?"None — and that is correct":"Simulated quantities"}</h2>
        {property_estimates.length===0&&<div className="muted">A property estimate exists only when the workflow is scientifically converged and the quantity maps onto a registered property with a valid unit. Anything less produces no number.</div>}
        {property_estimates.map(e=><div key={e.id} className="notice">
          <strong>{e.canonical_value} {e.canonical_unit}</strong>
          <div className="muted">origin {e.scientific_origin} · tolerance {e.numerical_tolerance??"n/a"} ({e.tolerance_basis??"—"})</div>
          <div className="muted">extractor {e.extractor_key} v{e.extractor_version} · checksum <code>{e.estimate_checksum.slice(0,14)}…</code></div>
          {e.method_limitations.slice(0,2).map((l,i)=><div key={i} className="muted">• {l}</div>)}
        </div>)}
      </div>
    </div>

    <div className="card">
      <div className="card-pad"><div className="eyebrow">Steps &amp; job attempts</div><h2>Immutable execution record</h2></div>
      <div className="table-wrap"><table>
        <thead><tr><th>Step</th><th>Attempt</th><th>Backend / command</th><th>Operational status</th><th>Exit / elapsed</th></tr></thead>
        <tbody>{jobs.map(j=>{const step=steps.find(s=>steps.indexOf(s)>=0);return <tr key={j.id}>
          <td>{steps[0]?.step_key}<div className="muted">input <code>{steps[0]?.input_checksum.slice(0,12)}…</code></div></td>
          <td>#{j.attempt_number}</td>
          <td>{j.compute_backend_key}<div className="muted"><code>{String((j.command_descriptor as {executable_key?:string}).executable_key??"in-process")}</code> · shell=false</div></td>
          <td><span className="badge">{j.status}</span>{j.failure_code&&<div className="muted">{j.failure_code}</div>}</td>
          <td>{j.process_exit_code??"—"} · {j.elapsed_seconds??0}s{step?"":""}</td>
        </tr>;})}</tbody>
      </table></div>
    </div>

    <div className="card">
      <div className="card-pad"><div className="eyebrow">Artifacts</div><h2>Checksummed provenance</h2></div>
      <div className="table-wrap"><table>
        <thead><tr><th>File</th><th>Type / role</th><th>SHA-256</th><th>Bytes</th><th>Preview</th></tr></thead>
        <tbody>{artifacts.map(a=><tr key={a.id}>
          <td><strong>{a.file_name}</strong>{a.truncated&&<div className="muted">truncated by output cap</div>}</td>
          <td>{a.artifact_type} / {a.content_role}</td>
          <td><code>{a.content_checksum.slice(0,16)}…</code></td>
          <td>{a.content_bytes}</td>
          <td><pre style={{fontSize:10,maxWidth:320,maxHeight:120,overflow:"auto",whiteSpace:"pre-wrap"}}>{a.inline_preview?.slice(0,600)}</pre></td>
        </tr>)}</tbody>
      </table></div>
    </div>
  </div>;
}
