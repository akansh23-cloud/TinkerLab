"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DecisionChart } from "@/lib/decision";
import { DecisionMatrix, EvidenceMix } from "@/components/charts/DecisionMatrix";
import { PropertyDeltas, RequirementMargins } from "@/components/charts/RequirementMargins";
import { ProjectPropertySpace } from "@/components/charts/ProjectPropertySpace";

/**
 * The visual half of the comparison view.
 *
 * Ordered the way the decision is actually made: first which candidates survive the hard gates
 * (matrix), then how much room the survivor has (margins), then what it costs you against the
 * incumbent (deltas), then what the whole answer is made of (evidence mix). Putting the evidence
 * mix last is deliberate — it is the check you run before acting, not the screen you browse.
 */
export function DecisionCharts({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<string>("");
  const chart = useQuery({
    queryKey: ["decision-chart", projectId],
    queryFn: () => api<DecisionChart>(`/replacement-projects/${projectId}/decision-chart`),
  });

  if (chart.isLoading) return <div className="empty">Building the decision view…</div>;
  if (chart.error || !chart.data) {
    return <div className="empty">Decision view unavailable: {(chart.error as Error)?.message}</div>;
  }

  const { candidates, requirements, baseline } = chart.data;
  const excludedCandidates = chart.data.excluded_candidates ?? [];
  if (!candidates.length) {
    return (
      <div className="empty">
        No candidates yet, so there is nothing to compare. Generate them in the Candidate Lab.
      </div>
    );
  }

  const active = candidates.find((c) => c.candidate_id === selected) ?? candidates[0];
  const hypotheses = candidates.filter((c) => c.candidate_kind === "hypothesis");
  const allUnknown = candidates.every((c) => (c.hard_passed ?? 0) + (c.hard_failed ?? 0) === 0);

  return (
    <div className="grid">
      {excludedCandidates.length > 0 && (
        <div className="notice">
          <strong>{excludedCandidates.length} candidate{excludedCandidates.length === 1 ? " was" : "s were"} not plotted.</strong>
          <div>The canonical evaluator could not process them. They remain in Candidate Lab for diagnosis; the chart no longer drops them silently.</div>
        </div>
      )}
      {hypotheses.length > 0 && allUnknown && (
        <div className="notice">
          <strong>Every cell is UNKNOWN, and that is the correct answer.</strong>
          <div>
            All {candidates.length} candidates are generated composition hypotheses. A hypothesis is a
            formulation nobody has made yet, so it has no measurements — and this platform will not
            inherit the baseline&rsquo;s properties to fill the grid in. To get decidable cells, either
            run the Prediction Lab to attach model estimates (which stay marked as predictions), or
            attach existing materials as candidates.
          </div>
        </div>
      )}
      <div className="card card-pad">
        <div className="eyebrow">Decision matrix</div>
        <h2>Which candidates clear the hard requirements</h2>
        <p className="muted" style={{ margin: "6px 0 14px" }}>
          One hard failure eliminates a candidate regardless of how well it scores elsewhere, so hard
          requirements are drawn first and ruled off from the soft ones.
        </p>
        <DecisionMatrix
          candidates={candidates}
          requirements={requirements}
          selectedCandidateId={active.candidate_id}
          onSelectCandidate={setSelected}
        />
      </div>

      <div className="card card-pad">
        <div className="eyebrow">Margins</div>
        <h2>{active.display_name} — headroom against each requirement</h2>
        <p className="muted" style={{ margin: "6px 0 14px" }}>
          Select a row in the matrix above to switch candidate. Positive is always better than
          required, whichever direction the requirement points.
        </p>
        <RequirementMargins cells={active.cells} requirements={requirements} />
      </div>

      <div className="card card-pad">
        <div className="eyebrow">Against the incumbent</div>
        <h2>{active.display_name} versus {baseline.display_name}</h2>
        <p className="muted" style={{ margin: "6px 0 14px" }}>
          What you gain and what you give up. A substitution that passes every requirement can still
          be a bad trade, and this is where that shows.
        </p>
        <PropertyDeltas properties={active.properties} />
      </div>

      <div className="card card-pad">
        <div className="eyebrow">Property space</div>
        <h2>Where the incumbent sits, and what else is in range</h2>
        <p className="muted" style={{ margin: "6px 0 14px" }}>
          The dashed ring is {baseline.display_name}. Anything inside the shaded box satisfies this
          study’s thresholds on both axes.
        </p>
        <ProjectPropertySpace baselineId={baseline.id} requirements={requirements} />
      </div>

      <div className="card card-pad">
        <div className="eyebrow">Evidence</div>
        <h2>What these answers are made of</h2>
        <EvidenceMix candidates={candidates} />
      </div>
    </div>
  );
}
