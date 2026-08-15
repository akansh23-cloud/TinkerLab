"use client";

import {useEffect, useMemo, useState} from "react";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {
  api, DecisionMatrix, DecisionMatrixRow, PortfolioBoard, ReplacementProgramRecord,
  ReplacementRecommendationRecord, ScientificActionRecord,
} from "@/lib/api";
import {IndustrialRig} from "./IndustrialRig";
import {InteractiveSpecimen3D, LabMode} from "./InteractiveSpecimen3D";


type Props={projectId:string};

const MODE_META:Record<LabMode,{label:string;short:string;description:string;keywords:string[]}>={
  thermal:{label:"Thermal / furnace",short:"Thermal",description:"Visualize a controlled heating or thermal-exposure setup.",keywords:["thermal","temperature","conductivity","oxidation","heat","phase"]},
  dielectric:{label:"Electrical breakdown",short:"Electrical",description:"Visualize a high-voltage dielectric or breakdown test setup.",keywords:["breakdown","dielectric","band_gap","electrical","voltage","resistivity"]},
  mechanical:{label:"Mechanical loading",short:"Mechanical",description:"Visualize tensile/compression loading and specimen deformation.",keywords:["tensile","yield","fracture","hardness","modulus","stress","mechanical"]},
};

function requirementMatches(row:DecisionMatrixRow,mode:LabMode){
  const hay=`${row.property_key??""} ${row.requirement_key} ${row.display_name}`.toLowerCase();
  return MODE_META[mode].keywords.some(k=>hay.includes(k));
}
function decisionFor(candidateId:string|undefined,board:PortfolioBoard|undefined,rec:ReplacementRecommendationRecord|undefined){
  if(!candidateId)return "UNKNOWN" as const;
  if(rec?.recommended_candidate_ids.includes(candidateId))return "ADVANCE" as const;
  if(rec?.rejected_candidate_ids.includes(candidateId))return "REJECT" as const;
  if(rec?.held_candidate_ids.includes(candidateId))return "HOLD / TEST" as const;
  const row=board?.candidates.find(c=>c.candidate_id===candidateId);
  if(row?.eligibility==="blocked")return "REJECT" as const;
  if(row?.gates_satisfied)return "ADVANCE" as const;
  return row ? "HOLD / TEST" as const : "UNKNOWN" as const;
}
function statusClass(status:string){const s=status.toUpperCase();return s==="PASS"?"pass":s==="FAIL"?"fail":"unknown";}
function decisionClass(decision:string){return decision==="ADVANCE"?"pass":decision==="REJECT"?"fail":"unknown";}

function CommandProfile({mode,progress,target}:{mode:LabMode;progress:number;target:number}){
  const points=Array.from({length:32},(_,i)=>{
    const x=14+i*(292/31);const f=i/31;const y=104-74*Math.min(1,f/Math.max(.01,progress||.01));return `${x},${y}`;
  }).join(" ");
  return <div className="lab-command-chart">
    <div className="chart-title">Command profile · not sensor data</div>
    <svg viewBox="0 0 320 126" role="img" aria-label={`${MODE_META[mode].short} command profile`}>
      <line x1="14" y1="104" x2="306" y2="104" stroke="#bdc9c4"/><line x1="14" y1="18" x2="14" y2="104" stroke="#bdc9c4"/>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1={14+292*progress} y1="18" x2={14+292*progress} y2="104" stroke="#7d8d87" strokeDasharray="4 4"/>
      <text x="17" y="20" fontSize="10" fill="#65736e">setpoint {target}</text><text x="250" y="119" fontSize="10" fill="#65736e">time →</text>
    </svg>
  </div>;
}

export function VirtualTestStudio({projectId}:Props){
  const [mode,setMode]=useState<LabMode>("thermal");
  const [candidateChoice,setCandidateChoice]=useState("");
  const [requirementChoice,setRequirementChoice]=useState("");
  const [temperature,setTemperature]=useState(525);
  const [voltage,setVoltage]=useState(30);
  const [load,setLoad]=useState(50);
  const [duration,setDuration]=useState(60);
  const [atmosphere,setAtmosphere]=useState("Inert / N₂");
  const [running,setRunning]=useState(false);
  const [progress,setProgress]=useState(0);
  const [completed,setCompleted]=useState(false);

  const programs=useQuery({queryKey:["lab-programs",projectId],queryFn:()=>api<ReplacementProgramRecord[]>(`/replacement-programs?project_id=${encodeURIComponent(projectId)}`)});
  const program=programs.data?.find(p=>p.is_demonstration_data)??programs.data?.[0];
  const enabled=!!program?.id;
  const board=useQuery({queryKey:["lab-portfolio",program?.id],enabled,queryFn:()=>api<PortfolioBoard>(`/replacement-programs/${program!.id}/portfolio`)});
  const matrix=useQuery({queryKey:["lab-matrix",program?.id],enabled,queryFn:()=>api<DecisionMatrix>(`/replacement-programs/${program!.id}/decision-matrix`)});
  const actions=useQuery({queryKey:["lab-actions",program?.id],enabled,queryFn:()=>api<ScientificActionRecord[]>(`/replacement-programs/${program!.id}/actions?status=open`)});
  const recommendation=useQuery({queryKey:["lab-recommendation",program?.id],enabled,queryFn:()=>api<ReplacementRecommendationRecord>(`/replacement-programs/${program!.id}/recommendation?preview=true`)});

  const candidateId=candidateChoice||board.data?.candidates[0]?.candidate_id||"";
  const candidate=board.data?.candidates.find(c=>c.candidate_id===candidateId);
  const relevantRows=useMemo(()=>{
    const rows=matrix.data?.rows??[];
    const matched=rows.filter(r=>requirementMatches(r,mode));
    return (matched.length?matched:rows.filter(r=>r.is_gating)).slice(0,6);
  },[matrix.data?.rows,mode]);
  const requirementId=requirementChoice&&relevantRows.some(r=>r.requirement_id===requirementChoice)?requirementChoice:relevantRows[0]?.requirement_id||"";
  const requirement=relevantRows.find(r=>r.requirement_id===requirementId);
  const cell=requirement&&candidateId?requirement.cells[candidateId]:undefined;
  const decision=decisionFor(candidateId,board.data,recommendation.data);
  const nextAction=(actions.data??[]).find(a=>a.candidate_id===candidateId&&(!requirementId||a.requirement_id===requirementId))
    ??(actions.data??[]).find(a=>a.candidate_id===candidateId);

  useEffect(()=>{setProgress(0);setCompleted(false);setRunning(false);setRequirementChoice("");},[mode,candidateId]);
  useEffect(()=>{
    if(!running)return;
    let raf=0;const started=performance.now();const length=6500;
    const step=(now:number)=>{const p=Math.min(1,(now-started)/length);setProgress(p);if(p<1)raf=requestAnimationFrame(step);else{setRunning(false);setCompleted(true);}};
    raf=requestAnimationFrame(step);return()=>cancelAnimationFrame(raf);
  },[running]);

  const target=mode==="thermal"?temperature:mode==="dielectric"?voltage:load;
  const intensity=Math.min(1,.12+progress*.8);
  const phase=!running?(completed?"Visualization complete":"Ready"):
    progress<.58?(mode==="thermal"?"Ramping temperature":mode==="dielectric"?"Ramping voltage":"Applying load"):
    progress<.9?(mode==="thermal"?"Holding exposure":"Maintaining setpoint"):"Completing visual cycle";


  return <section className="virtual-studio" data-testid="virtual-test-studio">
    <div className="virtual-studio-head">
      <div><div className="eyebrow">Virtual Experiment Lab · interactive test bay</div><h2>See the test. See the evidence. Understand the decision.</h2>
        <p className="muted">Configure an industrial test setup, animate the operating sequence, then compare the visualization with TinkerLab&apos;s authoritative evidence state. The animation never fabricates a measurement.</p></div>
    </div>

    <div className="lab-truth-strip">
      <div><span>1</span><strong>Configure</strong><small>Operator-defined test conditions</small></div>
      <div><span>2</span><strong>Visualize</strong><small>3D specimen + industrial rig</small></div>
      <div><span>3</span><strong>Compare evidence</strong><small>PASS / FAIL / UNKNOWN from TinkerLab</small></div>
      <div><span>4</span><strong>Act</strong><small>Advance / reject / next test</small></div>
    </div>

    <div className="lab-mode-tabs" role="tablist" aria-label="Virtual lab test mode">
      {(Object.keys(MODE_META) as LabMode[]).map(key=><button key={key} className={`lab-mode ${mode===key?"active":""}`} onClick={()=>setMode(key)}><strong>{MODE_META[key].label}</strong><span>{MODE_META[key].description}</span></button>)}
    </div>

    <div className="lab-main-grid">
      <div className="lab-scene-column">
        <div className="lab-scene-toolbar">
          <label>Candidate<select className="select" value={candidateId} onChange={e=>setCandidateChoice(e.target.value)} disabled={!board.data?.candidates.length}>
            {(board.data?.candidates??[]).map(c=><option key={c.candidate_id} value={c.candidate_id}>{c.display_name}</option>)}
          </select></label>
          <label>Requirement<select className="select" value={requirementId} onChange={e=>setRequirementChoice(e.target.value)} disabled={!relevantRows.length}>
            {relevantRows.map(r=><option key={r.requirement_id} value={r.requirement_id}>{r.display_name}</option>)}
          </select></label>
          <div className="lab-run-state"><span className={`lab-pulse ${running?"active":""}`}/><div><strong>{phase}</strong><span>{Math.round(progress*100)}% visual cycle</span></div></div>
        </div>
        <IndustrialRig mode={mode} progress={progress} running={running} temperature={temperature} voltage={voltage} load={load} atmosphere={atmosphere}/>
        <div className="lab-visual-row">
          <InteractiveSpecimen3D mode={mode} intensity={intensity} running={running} label={candidate?.display_name??"Candidate specimen"}/>
          <CommandProfile mode={mode} progress={progress} target={target}/>
        </div>
      </div>

      <aside className="lab-control-panel">
        <div className="eyebrow">Test controls</div><h3>{MODE_META[mode].label}</h3>
        {mode==="thermal"&&<>
          <label className="label">Target temperature <output>{temperature} K</output><input type="range" min="300" max="1400" step="25" value={temperature} onChange={e=>setTemperature(Number(e.target.value))}/></label>
          <label className="label">Exposure time <output>{duration} min</output><input type="range" min="5" max="240" step="5" value={duration} onChange={e=>setDuration(Number(e.target.value))}/></label>
          <label className="label">Atmosphere<select className="select" value={atmosphere} onChange={e=>setAtmosphere(e.target.value)}><option>Inert / N₂</option><option>Air</option><option>Vacuum</option><option>Reducing</option></select></label>
        </>}
        {mode==="dielectric"&&<>
          <label className="label">Applied voltage <output>{voltage} kV</output><input type="range" min="1" max="120" step="1" value={voltage} onChange={e=>setVoltage(Number(e.target.value))}/></label>
          <label className="label">Ramp duration <output>{duration} s</output><input type="range" min="5" max="180" step="5" value={duration} onChange={e=>setDuration(Number(e.target.value))}/></label>
        </>}
        {mode==="mechanical"&&<>
          <label className="label">Applied load <output>{load} kN</output><input type="range" min="1" max="250" step="1" value={load} onChange={e=>setLoad(Number(e.target.value))}/></label>
          <label className="label">Load-cycle duration <output>{duration} s</output><input type="range" min="5" max="180" step="5" value={duration} onChange={e=>setDuration(Number(e.target.value))}/></label>
        </>}
        <div className="lab-control-note"><strong>These are visualization setpoints.</strong> Changing them does not alter the scientific database or create evidence.</div>
        <button className="btn lab-run-btn" disabled={running} onClick={()=>{setCompleted(false);setProgress(0);setRunning(true);}}>{running?"Running visual cycle…":"Run virtual setup"}</button>
        <button className="btn btn-secondary" onClick={()=>{setProgress(0);setCompleted(false);setRunning(false);}}>Reset visualization</button>
      </aside>
    </div>

    <div className="lab-verdict-grid">
      <div className="card card-pad lab-evidence-card">
        <div className="eyebrow">Authoritative requirement state</div>
        <div className="lab-evidence-title"><h3>{requirement?.display_name??"No matching requirement"}</h3><span className={`badge ${statusClass(cell?.status??"UNKNOWN")}`}>{cell?.status??"UNKNOWN"}</span></div>
        {requirement&&<div className="lab-target-line"><span>Target</span><strong>{requirement.direction??"requirement"} {requirement.target_value??"—"} {requirement.target_unit??""}</strong></div>}
        <p>{cell?.why??"No authoritative evidence cell is available for this test category yet."}</p>
        {!!cell?.missing_evidence?.length&&<div className="lab-missing"><strong>Missing evidence</strong>{cell.missing_evidence.map(v=><span key={v}>{v}</span>)}</div>}
        <div className="lab-origin-line">Evidence coverage: {cell?`${Math.round(cell.coverage_score*100)}%`:"—"} · Origin: {cell?.governing_origin??"UNKNOWN"}</div>
      </div>

      <div className={`card card-pad lab-decision-card decision-${decisionClass(decision)}`}>
        <div className="eyebrow">Candidate decision</div><div className="lab-decision-big">{decision}</div>
        <p>{decision==="ADVANCE"?"Current gates are satisfied. Move to the next controlled qualification step.":decision==="REJECT"?"A definitive blocking failure prevents this candidate from being advanced.":decision==="HOLD / TEST"?"Do not guess. Resolve the blocking evidence gap before advancing.":"No authoritative candidate decision is available yet."}</p>
        {nextAction&&<div className="lab-next-action"><span>Next useful action</span><strong>{nextAction.action_type.replaceAll("_"," ")}</strong><small>{nextAction.reason}</small></div>}
        <div className="lab-decision-links">{program&&<Link href={`/projects/${projectId}/replacement`} className="btn btn-secondary">Open Mission Control</Link>}<Link href={`/projects/${projectId}/validation`} className="btn btn-secondary">Physical Validation</Link></div>
      </div>

      <div className="card card-pad lab-rationale-card">
        <div className="lab-rationale-title"><div><div className="eyebrow">Decision rationale</div><h3>Evidence, gaps, and next action</h3></div><span className="badge">Deterministic</span></div>
        <p><strong>{decision==="ADVANCE"?"Current blocking requirements are supported by sufficient evidence.":decision==="REJECT"?"At least one blocking requirement has definitive failure evidence.":decision==="HOLD / TEST"?"Evidence is incomplete or unresolved for one or more gating requirements.":"No authoritative decision is available yet."}</strong></p>
        <div className="rationale-columns">
          <div><span>What we know</span><ul>
            {relevantRows.map(r=>{const c=candidateId?r.cells[candidateId]:undefined;return <li key={r.requirement_id}><strong>{r.display_name}:</strong> {c?.status??"UNKNOWN"}{c?.why?` — ${c.why}`:""}</li>})}
          </ul></div>
          <div><span>What remains unresolved</span><ul>
            {relevantRows.flatMap(r=>{const c=candidateId?r.cells[candidateId]:undefined;return c?.missing_evidence?.map((v,i)=><li key={`${r.requirement_id}-${i}`}>{r.display_name}: {v}</li>)??[]})}
            {!relevantRows.some(r=>(candidateId?r.cells[candidateId]?.missing_evidence?.length:0))&&<li>No explicit missing-evidence item is recorded for the selected requirements.</li>}
          </ul></div>
        </div>
        <div className="rationale-next"><span>Next action</span><strong>{nextAction?nextAction.action_type.replaceAll("_"," "):decision==="ADVANCE"?"Proceed to controlled qualification":"Review evidence and define the next validation step"}</strong><small>{nextAction?.reason??"The action is derived directly from the replacement decision workflow."}</small></div>
        <small className="rationale-boundary">This panel is assembled directly from stored evidence, requirement states, and deterministic decision rules.</small>
      </div>
    </div>

    {!program&&<div className="notice"><strong>Setup-only mode.</strong> This project has no Phase-10 replacement programme yet, so the lab can visualize apparatus but cannot show evidence-linked PASS/FAIL/HOLD decisions.</div>}
    {completed&&<div className="lab-complete-banner"><strong>Visual cycle complete.</strong><span>No measurement was created. The decision above still comes from TinkerLab&apos;s evidence model. Record real results through Physical Validation or run an approved computational simulation through Simulation Lab.</span></div>}
  </section>;
}
