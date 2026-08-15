"use client";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { LabReadiness, ProjectReadiness, ReadinessCheck, ReadinessFix, ORGANISATION_CONFIGURED } from "@/lib/bench";

/**
 * Why a lab is unusable, and the button that fixes it.
 *
 * The labs were never wrong to refuse to run without their inputs. What they did wrong was refuse
 * silently: an empty dropdown and a disabled button, with no statement of what was missing. This
 * panel is the missing half of that contract.
 */

function StatusDot({ status }: { status: ReadinessCheck["status"] }) {
  const label = status === "ok" ? "Ready" : status === "warning" ? "Caution" : "Blocked";
  return <span className={`dot dot-${status}`} role="img" aria-label={label} title={label} />;
}

export function ConfigWarning() {
  if (ORGANISATION_CONFIGURED) return null;
  return (
    <div className="notice fail" style={{ marginBottom: 16 }}>
      <strong>Organisation scope is not configured.</strong>
      <div>
        Search spaces, candidate generation and virtual campaigns are organisation-scoped, so without{" "}
        <code>NEXT_PUBLIC_ORGANISATION_ID</code> the API returns “not found” for all of them and the labs
        appear empty. Set it in the web project’s environment variables and redeploy.
      </div>
    </div>
  );
}

function FixButton({ fix, onDone }: { fix: ReadinessFix; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: async () => {
      if (!fix.endpoint) return;
      await api(fix.endpoint, { method: fix.method ?? "POST" });
    },
    onSuccess: () => { setError(null); onDone(); },
    onError: (e: Error) => setError(e.message),
  });

  if (fix.kind === "navigate" && fix.href) {
    return <Link className="btn btn-secondary btn-sm" href={fix.href}>{fix.label}</Link>;
  }
  if (fix.kind !== "api" || !fix.endpoint) return null;
  return (
    <div>
      <button className="btn btn-sm" disabled={run.isPending} onClick={() => run.mutate()}>
        {run.isPending ? "Working…" : fix.label}
      </button>
      {error && <div className="prop-warn">{error}</div>}
    </div>
  );
}

function LabCard({ lab, onFixed }: { lab: LabReadiness; onFixed: () => void }) {
  const [expanded, setExpanded] = useState(lab.status !== "ok");
  const problems = lab.checks.filter((c) => c.status !== "ok");
  return (
    <div className={`card lab-card lab-${lab.status}`}>
      <div className="card-pad">
        <div className="topline" style={{ marginBottom: 8, alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <StatusDot status={lab.status} />
              <h2>{lab.display_name}</h2>
            </div>
            <p className="muted" style={{ margin: "6px 0 0" }}>{lab.purpose}</p>
          </div>
          {lab.status === "ok" ? (
            <Link className="btn btn-sm" href={lab.href}>Open</Link>
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={() => setExpanded(!expanded)}>
              {expanded ? "Hide" : `${problems.length} item${problems.length === 1 ? "" : "s"}`}
            </button>
          )}
        </div>

        {expanded && (
          <div className="check-list">
            {lab.checks.map((check) => (
              <div className="check-row" key={`${lab.key}-${check.code}`}>
                <StatusDot status={check.status} />
                <div>
                  <div className="check-label">{check.label}</div>
                  <div className="muted">{check.detail}</div>
                </div>
                <div>{check.fix && check.status !== "ok" && <FixButton fix={check.fix} onDone={onFixed} />}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ReadinessPanel({ projectId, focus }: { projectId: string; focus?: string }) {
  const qc = useQueryClient();
  const readiness = useQuery({
    queryKey: ["readiness", projectId],
    queryFn: () => api<ProjectReadiness>(`/replacement-projects/${projectId}/readiness`),
  });

  function refetchAll() {
    qc.invalidateQueries({ queryKey: ["readiness", projectId] });
    qc.invalidateQueries({ queryKey: ["search-spaces", projectId] });
    qc.invalidateQueries({ queryKey: ["project", projectId] });
    qc.invalidateQueries({ queryKey: ["candidate-lab", projectId] });
  }

  if (readiness.isLoading) return <div className="empty">Checking what this study needs…</div>;
  if (readiness.error || !readiness.data) return null;

  const labs = focus ? readiness.data.labs.filter((l) => l.key === focus) : readiness.data.labs;
  const { summary, next_action } = readiness.data;

  return (
    <div className="grid">
      <ConfigWarning />
      {next_action && (
        <div className="notice">
          <strong>Next step: {next_action.label}</strong>
          <div>{next_action.because}</div>
          <div style={{ marginTop: 10 }}>
            <FixButton fix={next_action} onDone={refetchAll} />
          </div>
        </div>
      )}
      {!next_action && summary.blocked === 0 && !focus && (
        <div className="notice pass">
          <strong>All inputs are in place.</strong>
          <div>{summary.ready_labs} of {summary.total_labs} labs are ready to run.</div>
        </div>
      )}
      <div className={focus ? "grid" : "grid grid-2"}>
        {labs.map((lab) => <LabCard key={lab.key} lab={lab} onFixed={refetchAll} />)}
      </div>
    </div>
  );
}

/** A compact inline blocker banner for a single lab page. */
export function LabGate({ projectId, labKey }: { projectId: string; labKey: string }) {
  const qc = useQueryClient();
  const readiness = useQuery({
    queryKey: ["readiness", projectId],
    queryFn: () => api<ProjectReadiness>(`/replacement-projects/${projectId}/readiness`),
  });
  const lab = readiness.data?.labs.find((l) => l.key === labKey);
  if (!lab || lab.status === "ok") return <ConfigWarning />;

  const blockers = lab.checks.filter((c) => c.status === "blocked");
  const cautions = lab.checks.filter((c) => c.status === "warning");
  if (!blockers.length && !cautions.length) return <ConfigWarning />;

  return (
    <>
      <ConfigWarning />
      <div className={`notice ${blockers.length ? "fail" : ""}`}>
        <strong>
          {blockers.length
            ? `This lab cannot run yet — ${blockers.length} missing input${blockers.length === 1 ? "" : "s"}`
            : "This lab will run, with caveats"}
        </strong>
        <div className="check-list" style={{ marginTop: 10 }}>
          {[...blockers, ...cautions].map((check) => (
            <div className="check-row" key={check.code}>
              <StatusDot status={check.status} />
              <div>
                <div className="check-label">{check.label}</div>
                <div className="muted">{check.detail}</div>
              </div>
              <div>
                {check.fix && (
                  <FixButton
                    fix={check.fix}
                    onDone={() => {
                      qc.invalidateQueries({ queryKey: ["readiness", projectId] });
                      qc.invalidateQueries({ queryKey: ["search-spaces", projectId] });
                    }}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
