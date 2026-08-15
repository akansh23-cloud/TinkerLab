"use client";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ProjectSummary } from "@/lib/api";
import { PlatformReadiness } from "@/lib/bench";
import { ConfigWarning } from "@/components/ReadinessPanel";

/**
 * The dashboard's job is to answer "what do I do now", which on a fresh deployment means
 * "there is nothing here yet, here is how to change that". A stat grid reading zero, zero, zero
 * with no route out is how a working system gets reported as broken.
 */
export default function Dashboard() {
  const qc = useQueryClient();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<ProjectSummary[]>("/replacement-projects"),
  });
  const readiness = useQuery({
    queryKey: ["platform-readiness"],
    queryFn: () => api<PlatformReadiness>("/bench/readiness"),
  });

  const installLibrary = useMutation({
    mutationFn: () => api<{ installed_count: number }>("/bench/install-reference-library", {
      method: "POST",
      body: JSON.stringify({}),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platform-readiness"] });
      qc.invalidateQueries({ queryKey: ["materials-index"] });
      qc.invalidateQueries({ queryKey: ["material-explorer"] });
    },
  });

  const active = projects.data?.filter((p) => p.status === "active").length ?? 0;
  const constraintCount = projects.data?.reduce((n, p) => n + p.constraint_count, 0) ?? 0;
  const candidateCount = projects.data?.reduce((n, p) => n + p.candidate_count, 0) ?? 0;
  const needsLibrary = (readiness.data?.material_count ?? 0) < 5;
  const noProjects = (projects.data?.length ?? 0) === 0;

  return (
    <>
      <div className="topline">
        <div>
          <div className="eyebrow">Material replacement workspace</div>
          <h1>Replacement studies</h1>
          <div className="muted">
            State what must hold, keep every source separable, and compare alternatives without inventing
            values for the gaps.
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn" href="/studies/new">New study</Link>
          <Link className="btn btn-secondary" href="/materials/new">Record a material</Link>
        </div>
      </div>

      <ConfigWarning />

      {needsLibrary && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <strong>This workspace has almost no materials in it.</strong>
          <div>
            Install the reference library to get 30+ real engineering grades across polymers, alloys,
            ceramics and composites &mdash; including a leaded brass and two fluoropolymers, so
            restriction-driven studies have a realistic incumbent to replace. Values are handbook-typical
            and recorded as such; they are never presented as measurements.
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center" }}>
            <button className="btn btn-sm" disabled={installLibrary.isPending} onClick={() => installLibrary.mutate()}>
              {installLibrary.isPending ? "Installing…" : "Install reference library"}
            </button>
            {installLibrary.isSuccess && (
              <span className="muted">Installed {installLibrary.data.installed_count} materials.</span>
            )}
            {installLibrary.error && (
              <span className="muted">{(installLibrary.error as Error).message}</span>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-3" style={{ marginBottom: 18 }}>
        <div className="card stat">
          <span className="kicker">Materials on file</span>
          <strong>{readiness.data?.material_count ?? "—"}</strong>
        </div>
        <div className="card stat">
          <span className="kicker">Active studies</span>
          <strong>{active}</strong>
        </div>
        <div className="card stat">
          <span className="kicker">Candidates under evaluation</span>
          <strong>{candidateCount}</strong>
        </div>
      </div>

      <div className="card">
        <div className="card-pad" style={{ borderBottom: "1px solid var(--line)" }}>
          <div className="topline" style={{ marginBottom: 0, alignItems: "center" }}>
            <h2>Studies</h2>
            <span className="muted">{constraintCount} formal requirement(s) across all studies</span>
          </div>
        </div>
        {projects.isLoading && <div className="empty">Loading workspace…</div>}
        {projects.error && <div className="empty">API unavailable: {(projects.error as Error).message}</div>}
        {projects.data && noProjects && (
          <div className="empty">
            No studies yet. Pick the material you want to replace and the reason you have to replace it —
            the study is created with a working search space, so its labs open ready to run.
            <div style={{ marginTop: 14 }}>
              <Link className="btn" href="/studies/new">Start a replacement study</Link>
            </div>
          </div>
        )}
        {projects.data && !noProjects && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Study</th><th>Baseline</th><th>Drivers</th><th>Requirements</th><th>Candidates</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {projects.data.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link href={`/projects/${p.id}`}><strong>{p.name}</strong></Link>
                      <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{p.description}</div>
                    </td>
                    <td>
                      <Link href={`/materials/${p.baseline_material.id}`}>{p.baseline_material.display_name}</Link>
                    </td>
                    <td>{p.replacement_reasons.join(", ")}</td>
                    <td>{p.constraint_count}</td>
                    <td>{p.candidate_count}</td>
                    <td><span className="badge">{p.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
