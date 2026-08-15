"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, API, ProjectSummary } from "@/lib/api";
import { PlatformReadiness } from "@/lib/bench";
import { ConfigWarning } from "@/components/ReadinessPanel";

type DeploymentStatus = {
  database_reachable: boolean;
  schema_ready: boolean;
  bootstrap_required: boolean;
  alembic_version?: string | null;
  expected_alembic_head?: string;
  organisation_id?: string;
  organisation_exists?: boolean;
  material_count?: number;
  reference_library_ready?: boolean;
  error?: string;
};

type BootstrapResult = {
  status: string;
  organisation_id: string;
  installed_count: number;
  skipped_count: number;
  deployment: DeploymentStatus;
};

/**
 * Dashboard + deployment gate.
 *
 * A fresh Vercel deployment can start with a completely empty Neon database. Before querying ORM
 * endpoints, ask the deployment endpoint (which is safe before migrations exist) whether the
 * schema, demo organisation and public reference library are present. Bootstrap is idempotent and
 * serialised server-side, so one first-load can make the workspace usable without a shell command.
 */
export default function Dashboard() {
  const qc = useQueryClient();
  const bootstrapAttempted = useRef(false);

  const deployment = useQuery({
    queryKey: ["deployment-status"],
    queryFn: () => api<DeploymentStatus>("/deployment/status"),
    retry: 1,
  });

  const bootstrap = useMutation({
    mutationFn: () => api<BootstrapResult>("/deployment/bootstrap", { method: "POST" }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["deployment-status"] });
      await qc.invalidateQueries({ queryKey: ["platform-readiness"] });
      await qc.invalidateQueries({ queryKey: ["projects"] });
      await qc.invalidateQueries({ queryKey: ["materials-index"] });
      await qc.invalidateQueries({ queryKey: ["material-explorer"] });
    },
  });

  useEffect(() => {
    if (deployment.data?.bootstrap_required && !bootstrapAttempted.current) {
      bootstrapAttempted.current = true;
      bootstrap.mutate();
    }
  }, [deployment.data?.bootstrap_required]); // mutation object is intentionally not a dependency

  const workspaceReady = deployment.data?.database_reachable === true && deployment.data?.bootstrap_required === false;

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<ProjectSummary[]>("/replacement-projects"),
    enabled: workspaceReady,
  });
  const readiness = useQuery({
    queryKey: ["platform-readiness"],
    queryFn: () => api<PlatformReadiness>("/bench/readiness"),
    enabled: workspaceReady,
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
      qc.invalidateQueries({ queryKey: ["deployment-status"] });
    },
  });

  const active = projects.data?.filter((p) => p.status === "active").length ?? 0;
  const constraintCount = projects.data?.reduce((n, p) => n + p.constraint_count, 0) ?? 0;
  const candidateCount = projects.data?.reduce((n, p) => n + p.candidate_count, 0) ?? 0;
  const needsLibrary = workspaceReady && (readiness.data?.material_count ?? 0) < 5;
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

      {deployment.isLoading && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <strong>Checking API and database…</strong>
          <div>TinkerLab is verifying the same-origin API at <code>{API}</code> before loading workspace data.</div>
        </div>
      )}

      {deployment.error && (
        <div className="notice fail" style={{ marginBottom: 18 }}>
          <strong>The frontend is running, but the TinkerLab API service is not reachable.</strong>
          <div style={{ marginTop: 6 }}>{(deployment.error as Error).message}</div>
          <div style={{ marginTop: 6 }}>
            On Vercel Phase 12.2.3 uses the hybrid <code>apps/web</code> deployment and serves FastAPI at <code>/api</code> on this same domain.
          </div>
        </div>
      )}

      {bootstrap.isPending && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <strong>Initializing the scientific workspace…</strong>
          <div>Applying database migrations, creating the deterministic demo organisation, and installing the public reference library. This operation is idempotent.</div>
        </div>
      )}

      {bootstrap.error && (
        <div className="notice fail" style={{ marginBottom: 18 }}>
          <strong>Workspace initialization failed.</strong>
          <div style={{ marginTop: 6 }}>{(bootstrap.error as Error).message}</div>
          <button
            className="btn btn-sm"
            style={{ marginTop: 10 }}
            onClick={() => { bootstrapAttempted.current = true; bootstrap.mutate(); }}
          >
            Retry initialization
          </button>
        </div>
      )}

      {workspaceReady && deployment.data && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <strong>API and database are ready.</strong>
          <div>
            Schema <code>{deployment.data.alembic_version ?? "unknown"}</code> · {deployment.data.material_count ?? 0} material(s) available · same-origin API <code>{API}</code>.
          </div>
        </div>
      )}

      {needsLibrary && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <strong>This workspace has almost no materials in it.</strong>
          <div>
            Install the reference library to get 30+ real engineering grades across polymers, alloys,
            ceramics and composites &mdash; including a leaded brass and two fluoropolymers. Values are
            handbook-typical and recorded as such; they are never presented as measurements.
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center" }}>
            <button className="btn btn-sm" disabled={installLibrary.isPending} onClick={() => installLibrary.mutate()}>
              {installLibrary.isPending ? "Installing…" : "Install reference library"}
            </button>
            {installLibrary.isSuccess && <span className="muted">Reference library installation completed.</span>}
            {installLibrary.error && <span className="muted">{(installLibrary.error as Error).message}</span>}
          </div>
        </div>
      )}

      <div className="grid grid-3" style={{ marginBottom: 18 }}>
        <div className="card stat">
          <span className="kicker">Materials on file</span>
          <strong>{readiness.data?.material_count ?? deployment.data?.material_count ?? "—"}</strong>
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
        {!workspaceReady && !deployment.error && <div className="empty">Preparing workspace…</div>}
        {projects.isLoading && workspaceReady && <div className="empty">Loading workspace…</div>}
        {projects.error && <div className="empty">API error: {(projects.error as Error).message}</div>}
        {projects.data && noProjects && (
          <div className="empty">
            No studies yet. The material library is ready; pick the material you want to replace and the
            reason it must be replaced. The study is created with a working search space so its labs open ready to run.
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
                    <td><Link href={`/materials/${p.baseline_material.id}`}>{p.baseline_material.display_name}</Link></td>
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
