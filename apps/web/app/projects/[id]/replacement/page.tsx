"use client";

// Replacement Mission Control — the flagship Phase-10 screen.
//
// The design rule throughout: the interface must not be able to imply more certainty than the
// evidence supports. Concretely that means UNKNOWN is always rendered explicitly rather than left
// blank, a rank is always shown next to what was excluded from it, a convergence percentage is
// always shown next to the words that say it is not a probability, and a recommendation is always
// shown next to the note that it is not a qualification decision.

import {use, useMemo, useState} from "react";
import Link from "next/link";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {
  api, CandidateExplanation, ConvergenceRecord, DecisionMatrix, EvidenceGapRecord,
  MatrixCell, PortfolioBoard, ProgramGaps, ProgramHeader, RankingResponse,
  ReplacementProgramRecord, ReplacementRecommendationRecord, ScientificActionRecord,
  TechnicalDossierRecord, TimelineEventRecord,
} from "@/lib/api";
import {MatrixCellBadge} from "@/components/MatrixCellBadge";
import {EvidenceGapBadge} from "@/components/EvidenceGapBadge";
import {ProgramStateBadge} from "@/components/ProgramStateBadge";
import {EligibilityBadge} from "@/components/EligibilityBadge";
import {ActionPriorityBadge} from "@/components/ActionPriorityBadge";
import {QualificationNotice} from "@/components/QualificationNotice";

const WORKFLOW_STEPS = [
  {key:"application", label:"Application context"},
  {key:"requirements", label:"Functional requirements"},
  {key:"incumbent", label:"Incumbent baseline"},
  {key:"candidates", label:"Candidate portfolio"},
  {key:"screening", label:"Scientific screening"},
  {key:"industrial", label:"Industrial viability"},
  {key:"experiments", label:"Experimental validation"},
  {key:"convergence", label:"Convergence"},
  {key:"recommendation", label:"Recommendation & dossier"},
];

// Which workflow step a program state has reached. Used only to highlight the stepper; the
// authoritative state always comes from the backend resolver.
const STEP_FOR_STATE: Record<string,number> = {
  draft:0, requirements_defined:1, candidates_generated:3, screening:4, validating:4,
  experimenting:6, converging:7, decision_ready:8, recommended:8, no_suitable_candidate:8,
  paused:0, archived:0,
};

const TABS = ["portfolio","matrix","gaps","actions","convergence","recommendation","timeline"] as const;
type Tab = typeof TABS[number];

function pct(value:number|undefined|null){ return value==null ? "—" : `${value.toFixed(1)}%`; }

export default function ReplacementMissionControl({params}:{params:Promise<{id:string}>}){
  const {id} = use(params);
  const qc = useQueryClient();
  const [tab,setTab] = useState<Tab>("portfolio");
  const [programChoice,setProgramChoice] = useState("");
  const [drawerCell,setDrawerCell] = useState<{requirement:string;candidate:string;cell:MatrixCell}|null>(null);
  const [explainFor,setExplainFor] = useState<string>("");
  const [eligibilityFilter,setEligibilityFilter] = useState<string>("all");

  const programs = useQuery({
    queryKey:["replacement-programs",id],
    queryFn:()=>api<ReplacementProgramRecord[]>(`/replacement-programs?project_id=${encodeURIComponent(id)}`),
  });
  const programId = programChoice || programs.data?.[0]?.id || "";
  const enabled = !!programId;

  const header = useQuery({queryKey:["p10-header",programId],enabled,
    queryFn:()=>api<ProgramHeader>(`/replacement-programs/${programId}/header`)});
  const board = useQuery({queryKey:["p10-portfolio",programId],enabled,
    queryFn:()=>api<PortfolioBoard>(`/replacement-programs/${programId}/portfolio`)});
  const matrix = useQuery({queryKey:["p10-matrix",programId],enabled,
    queryFn:()=>api<DecisionMatrix>(`/replacement-programs/${programId}/decision-matrix`)});
  const gaps = useQuery({queryKey:["p10-gaps",programId],enabled,
    queryFn:()=>api<ProgramGaps>(`/replacement-programs/${programId}/evidence-gaps`)});
  const actions = useQuery({queryKey:["p10-actions",programId],enabled,
    queryFn:()=>api<ScientificActionRecord[]>(`/replacement-programs/${programId}/actions?status=open`)});
  const convergence = useQuery({queryKey:["p10-convergence",programId],enabled,
    queryFn:()=>api<ConvergenceRecord>(`/replacement-programs/${programId}/convergence`)});
  const ranking = useQuery({queryKey:["p10-ranking",programId],enabled,
    queryFn:()=>api<RankingResponse>(`/replacement-programs/${programId}/ranking`)});
  const timeline = useQuery({queryKey:["p10-timeline",programId],enabled,
    queryFn:()=>api<TimelineEventRecord[]>(`/replacement-programs/${programId}/timeline?limit=100`)});
  const recommendation = useQuery({
    queryKey:["p10-recommendation",programId],enabled,
    queryFn:()=>api<ReplacementRecommendationRecord>(`/replacement-programs/${programId}/recommendation?preview=true`),
  });
  const explanation = useQuery({
    queryKey:["p10-explain",programId,explainFor],enabled:enabled&&!!explainFor,
    queryFn:()=>api<CandidateExplanation>(`/replacement-programs/${programId}/candidates/${explainFor}/explanation`),
  });

  const invalidate = ()=>{
    ["p10-header","p10-portfolio","p10-matrix","p10-gaps","p10-actions","p10-convergence",
     "p10-ranking","p10-timeline","p10-recommendation"].forEach(key=>
      qc.invalidateQueries({queryKey:[key,programId]}));
  };

  const reassess = useMutation({
    mutationFn:()=>api(`/replacement-programs/${programId}/reassess`,{method:"POST"}),
    onSuccess:invalidate,
  });
  const generateRecommendation = useMutation({
    mutationFn:()=>api(`/replacement-programs/${programId}/recommendation`,{method:"POST",body:JSON.stringify({})}),
    onSuccess:invalidate,
  });
  const generateDossier = useMutation({
    mutationFn:()=>api<TechnicalDossierRecord>(`/replacement-programs/${programId}/dossier`,{method:"POST",body:JSON.stringify({})}),
    onSuccess:invalidate,
  });

  const activeStep = STEP_FOR_STATE[header.data?.program_state ?? "draft"] ?? 0;
  const boardCandidates = board.data?.candidates;
  const filteredRows = useMemo(()=>{
    const rows = boardCandidates ?? [];
    return eligibilityFilter==="all" ? rows : rows.filter(r=>r.eligibility===eligibilityFilter);
  },[boardCandidates,eligibilityFilter]);

  if(programs.isLoading) return <main className="page"><p>Loading replacement programmes…</p></main>;
  if(programs.error) return <main className="page"><p className="error">{String(programs.error)}</p></main>;
  if(!programs.data?.length){
    return <main className="page">
      <h1>Replacement Mission Control</h1>
      <p>This project has no replacement programme yet. A programme binds one application role, one
         incumbent material state and one candidate portfolio to a decision policy.</p>
      <Link href={`/projects/${id}`}>Back to project</Link>
    </main>;
  }

  return <main className="page" data-testid="replacement-mission-control">
    <header className="program-header">
      <div className="row">
        <h1>Replacement Mission Control</h1>
        <select aria-label="Replacement programme" value={programId}
                onChange={e=>setProgramChoice(e.target.value)}>
          {programs.data.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {header.data?.is_demonstration_data && (
        <div className="notice" role="note" data-testid="demo-notice">
          <strong>Demonstration data.</strong> Every candidate material and every value in this
          programme is synthetic. Nothing here is a measurement of a real substance.
        </div>
      )}

      {header.data && <dl className="header-grid">
        <div><dt>Application</dt><dd>{header.data.application_name ?? "UNKNOWN"}</dd></div>
        <div><dt>Incumbent</dt>
          <dd>{header.data.incumbent_material.display_name ?? "UNKNOWN"}
            {header.data.incumbent_state.label ? ` — ${header.data.incumbent_state.label}` : ""}</dd></div>
        <div><dt>Programme state</dt><dd><ProgramStateBadge state={header.data.program_state}/></dd></div>
        <div><dt>Convergence</dt>
          <dd>{header.data.convergence_state ?? "NOT ASSESSED"}{" "}
            <span title="Completed decision work — not a probability of success">
              ({pct(header.data.convergence_progress_percent)})
            </span></dd></div>
        <div><dt>Active candidates</dt><dd>{header.data.active_candidates}</dd></div>
        <div><dt>Blocked candidates</dt><dd>{header.data.blocked_candidates}</dd></div>
        <div><dt>Blocking gaps</dt><dd>{header.data.blocking_gaps}</dd></div>
        <div><dt>Decision policy</dt><dd>v{header.data.decision_policy_version}</dd></div>
      </dl>}

      <ol className="stepper" data-testid="workflow-stepper">
        {WORKFLOW_STEPS.map((step,index)=>
          <li key={step.key} data-active={index===activeStep} data-complete={index<activeStep}>
            <span className="step-index">{index+1}</span> {step.label}
          </li>)}
      </ol>

      <div className="row actions">
        <button onClick={()=>reassess.mutate()} disabled={reassess.isPending}>
          {reassess.isPending ? "Reassessing…" : "Reassess programme"}
        </button>
        <button onClick={()=>generateRecommendation.mutate()} disabled={generateRecommendation.isPending}>
          Generate recommendation
        </button>
        <button onClick={()=>generateDossier.mutate()} disabled={generateDossier.isPending}>
          Generate technical dossier
        </button>
      </div>
    </header>

    <nav className="tabs" role="tablist">
      {TABS.map(name=>
        <button key={name} role="tab" aria-selected={tab===name} onClick={()=>setTab(name)}>
          {name[0].toUpperCase()+name.slice(1)}
        </button>)}
    </nav>

    {/* ---------------------------------------------------------------- portfolio */}
    {tab==="portfolio" && <section aria-label="Candidate portfolio">
      <div className="row">
        <label>Filter by eligibility{" "}
          <select value={eligibilityFilter} onChange={e=>setEligibilityFilter(e.target.value)}>
            <option value="all">All</option>
            <option value="eligible">Eligible</option>
            <option value="unresolved">Unresolved</option>
            <option value="blocked">Blocked</option>
          </select>
        </label>
        {board.data && <span className="counts">
          {board.data.counts.eligible} eligible · {board.data.counts.unresolved} unresolved ·{" "}
          {board.data.counts.blocked} blocked
        </span>}
      </div>

      <div className="incumbent-compare">
        <h2>Incumbent versus candidates</h2>
        <p className="muted">
          The incumbent column shows what is actually recorded for the incumbent material. Where no
          value exists it reads UNKNOWN rather than being filled in from a plausible reference.
        </p>
      </div>

      <table className="grid">
        <thead><tr>
          <th>Candidate</th><th>Eligibility</th><th>Portfolio state</th><th>Rank</th>
          <th>Coverage</th><th>Blocking gaps</th><th>Conflicts</th><th>Next action</th><th></th>
        </tr></thead>
        <tbody>
          {filteredRows.map(row=>
            <tr key={row.candidate_id} data-testid={`portfolio-row-${row.candidate_id}`}>
              <td>{row.display_name}{row.pareto_front && <span className="badge">PARETO FRONT</span>}</td>
              <td><EligibilityBadge eligibility={row.eligibility}/></td>
              <td>{row.portfolio_state.replace(/_/g," ")}</td>
              <td>{row.rank ?? <span title={row.rank_excluded_reason ?? ""}>NOT RANKED</span>}</td>
              <td>{(row.evidence_coverage*100).toFixed(0)}%</td>
              <td>{row.blocking_gap_count}</td>
              <td>{row.conflict_count}</td>
              <td>{row.next_action
                ? <>{row.next_action.action_type.replace(/_/g," ")}{" "}
                    <ActionPriorityBadge priority={row.next_action.priority}
                      factors={row.next_action.priority_factors}/></>
                : "—"}</td>
              <td><button onClick={()=>setExplainFor(row.candidate_id)}>Explain</button></td>
            </tr>)}
        </tbody>
      </table>

      {ranking.data && <div className="ranking-note">
        <p className="muted">{ranking.data.note}</p>
        {ranking.data.excluded.length>0 && <details>
          <summary>{ranking.data.excluded.length} candidate(s) excluded from ranking</summary>
          <ul>{ranking.data.excluded.map(e=>
            <li key={e.candidate_id}><strong>{e.display_name}</strong> — {e.reason}</li>)}</ul>
        </details>}
        {ranking.data.sensitivity && <p data-testid="ranking-stability">
          Ranking stability: <strong>{ranking.data.sensitivity.stability.replace(/_/g," ")}</strong>{" "}
          — {ranking.data.sensitivity.reason}
        </p>}
      </div>}

      {explainFor && explanation.data && <aside className="drawer" data-testid="explanation-drawer">
        <button className="close" onClick={()=>setExplainFor("")}>Close</button>
        <h3>{explanation.data.display_name}</h3>
        <dl>
          <dt>Why it was proposed</dt><dd>{explanation.data.why_proposed}</dd>
          <dt>Why it is blocked</dt><dd>{explanation.data.why_blocked}</dd>
          <dt>Why an experiment is recommended</dt><dd>{explanation.data.why_experiment_recommended}</dd>
          <dt>Why it ranks where it does</dt><dd>{explanation.data.why_ranked}</dd>
        </dl>
        <p className="muted">{explanation.data.llm_boundary_note}</p>
      </aside>}
    </section>}

    {/* ---------------------------------------------------------------- matrix */}
    {tab==="matrix" && matrix.data && <section aria-label="Decision matrix">
      <p className="muted">{matrix.data.note}</p>
      <table className="grid matrix">
        <thead><tr>
          <th>Requirement</th><th>Criticality</th>
          {matrix.data.candidates.map(c=><th key={c.candidate_id}>{c.display_name}</th>)}
        </tr></thead>
        <tbody>
          {matrix.data.rows.map(row=>
            <tr key={row.requirement_id} data-gating={row.is_gating}>
              <td>
                <strong>{row.display_name}</strong>
                <div className="muted">
                  {row.property_key} {row.direction} {row.target_value ?? ""} {row.target_unit ?? ""}
                </div>
              </td>
              <td>{row.criticality.toUpperCase()}{!row.is_gating && <div className="muted">not gating</div>}</td>
              {matrix.data!.candidates.map(c=>{
                const cell = row.cells[c.candidate_id];
                if(!cell) return <td key={c.candidate_id}>—</td>;
                return <td key={c.candidate_id}>
                  <button className="cell-button"
                    onClick={()=>setDrawerCell({requirement:row.display_name,candidate:c.display_name,cell})}>
                    <MatrixCellBadge status={cell.status}/>
                  </button>
                </td>;
              })}
            </tr>)}
        </tbody>
      </table>

      {drawerCell && <aside className="drawer" data-testid="evidence-drawer">
        <button className="close" onClick={()=>setDrawerCell(null)}>Close</button>
        <h3>{drawerCell.requirement}</h3>
        <p>{drawerCell.candidate}</p>
        <p><MatrixCellBadge status={drawerCell.cell.status}/></p>
        <p>{drawerCell.cell.why}</p>
        <dl>
          <dt>Governing origin</dt><dd>{drawerCell.cell.governing_origin ?? "NONE"}</dd>
          <dt>Evidence coverage</dt><dd>{(drawerCell.cell.coverage_score*100).toFixed(0)}%</dd>
          <dt>Missing evidence</dt>
          <dd>{drawerCell.cell.missing_evidence.length ? drawerCell.cell.missing_evidence.join(", ") : "none"}</dd>
        </dl>
        <h4>Every origin considered</h4>
        <ul>{drawerCell.cell.outcomes.map((o,i)=>
          <li key={i}><code>{JSON.stringify(o)}</code></li>)}</ul>
      </aside>}
    </section>}

    {/* ---------------------------------------------------------------- gaps */}
    {tab==="gaps" && gaps.data && <section aria-label="Evidence gaps">
      <p className="muted">{gaps.data.note}</p>
      {Object.entries(gaps.data.by_class).filter(([,list])=>list.length>0).map(([gapClass,list])=>
        <div key={gapClass} className="gap-group">
          <h3><EvidenceGapBadge gapClass={gapClass}/> {list.length}</h3>
          <ul>{(list as EvidenceGapRecord[]).map(gap=>
            <li key={gap.gap_id}>
              <strong>{gap.candidate_display_name}</strong> — {gap.display_name ?? gap.requirement_key}
              <div className="muted">{gap.why_unresolved}</div>
              <div>What would resolve it: {gap.what_would_resolve_it}</div>
            </li>)}</ul>
        </div>)}
    </section>}

    {/* ---------------------------------------------------------------- actions */}
    {tab==="actions" && <section aria-label="Next action queue">
      <p className="muted">
        Actions are proposed deterministically and ordered by a transparent decision-value score.
        Recommending an action never starts it.
      </p>
      <table className="grid">
        <thead><tr>
          <th>Priority</th><th>Action</th><th>Candidate</th><th>Requirement</th>
          <th>Why</th><th>Status</th>
        </tr></thead>
        <tbody>
          {(actions.data ?? []).map(action=>
            <tr key={action.id ?? action.action_signature}>
              <td><ActionPriorityBadge priority={action.priority} factors={action.priority_factors}/></td>
              <td>{action.action_type.replace(/_/g," ")}</td>
              <td>{action.candidate_display_name ?? action.candidate_id ?? "—"}</td>
              <td>{action.requirement_key ?? "—"}</td>
              <td>{action.reason}</td>
              <td>{action.status}{action.depends_on.length>0 &&
                <div className="muted">blocked by {action.depends_on.length} prerequisite(s)</div>}</td>
            </tr>)}
        </tbody>
      </table>
    </section>}

    {/* ---------------------------------------------------------------- convergence */}
    {tab==="convergence" && convergence.data && <section aria-label="Convergence">
      <h2>{convergence.data.convergence_state.replace(/_/g," ").toUpperCase()}</h2>
      <div className="progress" data-testid="convergence-progress">
        <div className="bar" style={{width:`${convergence.data.presentation_progress_percent}%`}}/>
      </div>
      <p><strong>{pct(convergence.data.presentation_progress_percent)}</strong></p>
      <p className="notice" data-testid="convergence-disclaimer">
        {convergence.data.probability_disclaimer}
      </p>
      <ul>{convergence.data.reasons.map((reason,i)=><li key={i}>{reason}</li>)}</ul>
      <h3>Underlying counts</h3>
      <table className="grid"><tbody>
        {Object.entries(convergence.data.metrics).map(([key,value])=>
          <tr key={key}><th>{key.replace(/_/g," ")}</th><td>{value}</td></tr>)}
      </tbody></table>
    </section>}

    {/* ---------------------------------------------------------------- recommendation */}
    {tab==="recommendation" && recommendation.data && <section aria-label="Replacement recommendation">
      <h2 data-testid="recommendation-status">
        {recommendation.data.status.replace(/_/g," ").toUpperCase()}
      </h2>
      <QualificationNotice note={recommendation.data.qualification_note}/>
      <p>{recommendation.data.rationale}</p>

      {recommendation.data.status==="no_suitable_candidate" && <div data-testid="no-candidate-options">
        <h3>What this programme could do next</h3>
        <ul>{(recommendation.data.possible_program_actions ?? []).map((step,i)=>
          <li key={i}>{step}</li>)}</ul>
        <p className="muted">{recommendation.data.requirement_relaxation_note}</p>
      </div>}

      <h3>Per candidate</h3>
      <table className="grid">
        <thead><tr><th>Candidate</th><th>Outcome</th><th>Reason codes</th></tr></thead>
        <tbody>
          {recommendation.data.per_candidate.map((row,i)=>
            <tr key={i}>
              <td>{String(row.display_name)}</td>
              <td>{String(row.eligibility)}{row.gates_satisfied ? " — all gates satisfied" : ""}</td>
              <td>{(row.reason_codes as string[] ?? []).join(", ")}</td>
            </tr>)}
        </tbody>
      </table>

      <p className="muted">
        Decision policy v{recommendation.data.decision_policy_version} ·{" "}
        methodology {Object.entries(recommendation.data.methodology_versions)
          .map(([k,v])=>`${k}=${v}`).join(", ")}
      </p>
    </section>}

    {/* ---------------------------------------------------------------- timeline */}
    {tab==="timeline" && <section aria-label="Programme timeline">
      <ol className="timeline">
        {(timeline.data ?? []).map(event=>
          <li key={event.id}>
            <time>{new Date(event.occurred_at).toLocaleString()}</time>
            <strong>{event.event_kind.replace(/_/g," ")}</strong>
            <div>{event.summary}</div>
          </li>)}
      </ol>
    </section>}

    <footer>
      <Link href={`/projects/${id}`}>Back to project</Link>
    </footer>
  </main>;
}
