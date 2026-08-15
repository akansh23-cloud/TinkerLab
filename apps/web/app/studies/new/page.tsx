"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  ApplicationPreset, DerivedRequirementSet, MaterialIndexEntry, ReplacementDriver, RequirementTemplate, StudyResult,
} from "@/lib/bench";
import { ConfigWarning } from "@/components/ReadinessPanel";

type RequirementDraft = RequirementTemplate & { include: boolean };

function toDraft(template: RequirementTemplate): RequirementDraft {
  return { ...template, include: true };
}

function StudyWizard() {
  const search = useSearchParams();
  const presetBaseline = search.get("baseline") ?? "";

  const [step, setStep] = useState(1);
  const [baseline, setBaseline] = useState(presetBaseline);
  const [materialFilter, setMaterialFilter] = useState("");
  const [drivers, setDrivers] = useState<string[]>([]);
  const [presetKey, setPresetKey] = useState<string>("");
  const [useBaselineFloors, setUseBaselineFloors] = useState(true);
  const [margin, setMargin] = useState(5);
  const [requirements, setRequirements] = useState<RequirementDraft[]>([]);
  const [name, setName] = useState("");
  const [touchedRequirements, setTouchedRequirements] = useState(false);
  const [result, setResult] = useState<StudyResult | null>(null);

  const materials = useQuery({
    queryKey: ["materials-index", materialFilter],
    queryFn: () => api<MaterialIndexEntry[]>(
      `/bench/materials-index${materialFilter ? `?q=${encodeURIComponent(materialFilter)}` : ""}`,
    ),
  });
  const presets = useQuery({
    queryKey: ["application-presets"],
    queryFn: () => api<ApplicationPreset[]>("/bench/application-presets"),
  });
  const driverOptions = useQuery({
    queryKey: ["replacement-drivers"],
    queryFn: () => api<ReplacementDriver[]>("/bench/replacement-drivers"),
  });
  const derived = useQuery({
    queryKey: ["derived-requirements", baseline, margin],
    enabled: Boolean(baseline),
    queryFn: () => api<DerivedRequirementSet>(
      `/bench/materials/${baseline}/derived-requirements?margin=${(margin / 100).toFixed(3)}`,
    ),
  });

  const ctx = useQuery({
    queryKey: ["demo-context"],
    queryFn: () => api<{ organisation_id: string; user_id: string }>("/demo-context"),
  });

  const chosenMaterial = materials.data?.find((m) => m.id === baseline);
  const chosenPreset = presets.data?.find((p) => p.key === presetKey);

  // Requirements are recomposed whenever the inputs behind them change, until the user edits the
  // table. After that their edits win — silently rebuilding over someone's typed thresholds is the
  // fastest way to make a wizard untrustworthy.
  const composed = useMemo(() => {
    const rows: RequirementDraft[] = [];
    const seen = new Set<string>();
    for (const template of chosenPreset?.requirements ?? []) {
      rows.push(toDraft(template));
      seen.add(template.property_key);
    }
    if (useBaselineFloors) {
      for (const requirement of derived.data?.requirements ?? []) {
        if (seen.has(requirement.property_key)) continue;
        rows.push(toDraft(requirement));
        seen.add(requirement.property_key);
      }
    }
    return rows;
  }, [chosenPreset, useBaselineFloors, derived.data]);

  useEffect(() => {
    if (!touchedRequirements) setRequirements(composed);
  }, [composed, touchedRequirements]);

  useEffect(() => {
    if (!name && chosenMaterial) {
      setName(`Replace ${chosenMaterial.display_name}`);
    }
  }, [chosenMaterial, name]);

  const included = requirements.filter((r) => r.include);
  const hardCount = included.filter((r) => r.hard_or_soft === "hard").length;

  const create = useMutation({
    mutationFn: () =>
      api<StudyResult>("/bench/studies", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim() || "Replacement study",
          baseline_material_id: baseline,
          drivers: drivers.length ? drivers : ["cost"],
          preset_key: presetKey || null,
          derive_from_baseline: false,
          derive_space: true,
          organisation_id: ctx.data?.organisation_id ?? null,
          created_by: ctx.data?.user_id ?? null,
          requirements: included.map((r) => ({
            property_key: r.property_key,
            comparator: r.comparator,
            target_value: r.target_value,
            target_value_upper: r.target_value_upper,
            target_boolean: r.target_boolean,
            target_unit: r.target_unit,
            hard_or_soft: r.hard_or_soft,
            weight: r.weight,
            severity: r.severity,
            rationale: r.rationale,
          })),
          objectives: (chosenPreset?.objectives ?? []).map((o) => ({
            property_key: o.property_key,
            direction: o.direction,
            weight: o.weight,
            priority: o.priority,
            rationale: o.rationale,
          })),
        }),
      }),
    onSuccess: setResult,
  });

  function updateRequirement(index: number, patch: Partial<RequirementDraft>) {
    setTouchedRequirements(true);
    setRequirements(requirements.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  if (result) {
    return (
      <div className="grid">
        <div className="topline">
          <div>
            <div className="eyebrow">Study created</div>
            <h1>{result.project_name}</h1>
            <div className="muted">
              {result.requirement_count} requirement(s), {result.objective_count} objective(s).
            </div>
          </div>
        </div>

        <div className={`notice ${result.search_space_activated ? "pass" : ""}`}>
          <strong>
            {result.search_space_activated
              ? "Search space derived and activated — the labs are ready."
              : "Search space not derived."}
          </strong>
          <div>
            {result.search_space_activated
              ? "Bounded variation bands were derived from the baseline composition, with the matrix as the balance component. Widen them in the Candidate Lab if the study needs a broader space."
              : "Candidate generation needs a baseline composition with numeric amounts. Everything else in the study is saved."}
          </div>
          {result.notes.map((note, i) => <div className="muted" key={i}>{note}</div>)}
        </div>

        {result.rejected_requirements.length > 0 && (
          <div className="notice">
            <strong>{result.rejected_requirements.length} item(s) not applied</strong>
            {result.rejected_requirements.map((r) => (
              <div className="muted" key={r.property_key}>{r.property_key}: {r.reason}</div>
            ))}
          </div>
        )}

        <div className="grid grid-3">
          <Link className="btn" href={`/projects/${result.project_id}`}>Open the study</Link>
          <Link className="btn btn-secondary" href={`/projects/${result.project_id}/candidate-lab`}>Candidate Lab</Link>
          <Link className="btn btn-secondary" href={`/projects/${result.project_id}/virtual-lab`}>Virtual Experiment Lab</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="topline">
        <div>
          <div className="eyebrow">New replacement study</div>
          <h1>What are you replacing, and why?</h1>
          <div className="muted">
            Three steps. The study is created with its requirements and a working search space, so the labs
            open ready to run.
          </div>
        </div>
        <Link className="btn btn-secondary" href="/materials/new">Record a material first</Link>
      </div>

      <ConfigWarning />

      <div className="wizard-steps" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {[1, 2, 3].map((i) => <div key={i} className={`wizard-step ${i <= step ? "active" : ""}`} />)}
      </div>

      {step === 1 && (
        <div className="card card-pad grid">
          <h2>1 · The incumbent</h2>
          <p className="muted">The material currently in the part. Its recorded evidence sets the floor you have to hold.</p>
          <input
            className="input"
            placeholder="Search materials"
            value={materialFilter}
            onChange={(e) => setMaterialFilter(e.target.value)}
          />
          {materials.data?.length === 0 && (
            <div className="notice">
              <strong>No materials to choose from.</strong>
              <div>Record one, or install the reference library from the dashboard.</div>
              <div style={{ marginTop: 10 }}>
                <Link className="btn btn-sm" href="/materials/new">Record a material</Link>
              </div>
            </div>
          )}
          <div className="pick-list">
            {materials.data?.slice(0, 40).map((material) => (
              <label key={material.id} className={`pick-row ${baseline === material.id ? "pick-selected" : ""}`}>
                <input
                  type="radio"
                  name="baseline"
                  checked={baseline === material.id}
                  onChange={() => setBaseline(material.id)}
                />
                <span>
                  <strong>{material.display_name}</strong>
                  <span className="badge" style={{ marginLeft: 8 }}>{material.material_family}</span>
                  <div className="muted">
                    {material.observation_count} recorded propert{material.observation_count === 1 ? "y" : "ies"}
                    {material.description ? ` · ${material.description}` : ""}
                  </div>
                </span>
              </label>
            ))}
          </div>
          {chosenMaterial && chosenMaterial.observation_count === 0 && (
            <div className="notice fail">
              <strong>This material has no recorded properties.</strong>
              <div>Every comparison against it would resolve to UNKNOWN. Add its data first.</div>
              <div style={{ marginTop: 10 }}>
                <Link className="btn btn-sm" href={`/materials/${chosenMaterial.id}/add-data`}>Add property data</Link>
              </div>
            </div>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="grid">
          <div className="card card-pad grid">
            <h2>2 · Why replace it?</h2>
            <p className="muted">This is recorded on the study and shapes how the recommendation is framed.</p>
            <div className="grid grid-2">
              {driverOptions.data?.map((driver) => (
                <label key={driver.key} className={`pick-row ${drivers.includes(driver.key) ? "pick-selected" : ""}`}>
                  <input
                    type="checkbox"
                    checked={drivers.includes(driver.key)}
                    onChange={(e) =>
                      setDrivers(e.target.checked ? [...drivers, driver.key] : drivers.filter((d) => d !== driver.key))
                    }
                  />
                  <span>
                    <strong>{driver.display_name}</strong>
                    <div className="muted">{driver.description}</div>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="card card-pad grid">
            <h2>The application</h2>
            <p className="muted">
              Picking an application class fills in the requirements an engineer would open with for that
              duty. They are a defensible starting point, not a specification — review them on the next step.
            </p>
            <div className="pick-list">
              <label className={`pick-row ${presetKey === "" ? "pick-selected" : ""}`}>
                <input type="radio" name="preset" checked={presetKey === ""} onChange={() => { setPresetKey(""); setTouchedRequirements(false); }} />
                <span>
                  <strong>No application template</strong>
                  <div className="muted">Requirements come only from the incumbent’s own measured properties.</div>
                </span>
              </label>
              {presets.data?.map((preset) => (
                <label key={preset.key} className={`pick-row ${presetKey === preset.key ? "pick-selected" : ""}`}>
                  <input
                    type="radio"
                    name="preset"
                    checked={presetKey === preset.key}
                    onChange={() => { setPresetKey(preset.key); setTouchedRequirements(false); }}
                  />
                  <span>
                    <strong>{preset.display_name}</strong>
                    <span className="badge" style={{ marginLeft: 8 }}>{preset.sector}</span>
                    {chosenMaterial && preset.expected_family !== chosenMaterial.material_family && (
                      <span className="badge unknown" style={{ marginLeft: 6 }}>
                        written for {preset.expected_family}
                      </span>
                    )}
                    <div className="muted">{preset.summary}</div>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {chosenPreset && (
            <div className="grid grid-2">
              <div className="card card-pad">
                <div className="eyebrow">Assumptions</div>
                <ul className="tight-list">
                  {chosenPreset.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
              <div className="card card-pad">
                <div className="eyebrow">Watch out for</div>
                <ul className="tight-list">
                  {chosenPreset.watch_outs.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            </div>
          )}

          <div className="card card-pad">
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={useBaselineFloors}
                onChange={(e) => { setUseBaselineFloors(e.target.checked); setTouchedRequirements(false); }}
              />
              <span>
                <strong>Also hold the incumbent’s current performance</strong>
                <div className="muted">
                  Adds a floor for every property the incumbent has measured, with a margin, wherever the
                  application template does not already state a requirement.
                </div>
              </span>
            </label>
            {useBaselineFloors && (
              <label className="label" style={{ marginTop: 12, maxWidth: 280 }}>
                Margin below the incumbent: {margin}%
                <input
                  type="range"
                  min={0}
                  max={25}
                  value={margin}
                  onChange={(e) => { setMargin(Number(e.target.value)); setTouchedRequirements(false); }}
                />
              </label>
            )}
            {derived.data && derived.data.skipped.length > 0 && (
              <p className="muted" style={{ marginTop: 10 }}>
                {derived.data.skipped.length} propert{derived.data.skipped.length === 1 ? "y" : "ies"} could not be
                turned into a threshold automatically — mostly properties with no universally better direction,
                such as thermal conductivity, where the requirement depends on the job.
              </p>
            )}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="grid">
          <div className="card card-pad">
            <h2>3 · Review the requirements</h2>
            <p className="muted">
              {included.length} requirement(s), {hardCount} of them hard. A hard requirement can eliminate a
              candidate; a soft one only ranks it.
            </p>
            <label className="label" style={{ marginTop: 12 }}>
              Study name
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>

          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Use</th><th>Requirement</th><th>Test</th><th>Target</th><th>Strength</th><th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {requirements.map((requirement, index) => (
                    <tr key={`${requirement.property_key}-${index}`} className={requirement.include ? "" : "row-muted"}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Include ${requirement.property_key}`}
                          checked={requirement.include}
                          onChange={(e) => updateRequirement(index, { include: e.target.checked })}
                        />
                      </td>
                      <td>
                        <strong>{requirement.property_key.replaceAll("_", " ")}</strong>
                        <div className="muted"><code>{requirement.property_key}</code></div>
                      </td>
                      <td>{requirement.comparator}</td>
                      <td>
                        {requirement.comparator === "boolean" ? (
                          <select
                            className="select"
                            value={String(requirement.target_boolean)}
                            onChange={(e) => updateRequirement(index, { target_boolean: e.target.value === "true" })}
                          >
                            <option value="true">must be yes</option>
                            <option value="false">must be no</option>
                          </select>
                        ) : (
                          <div style={{ display: "flex", gap: 6 }}>
                            <input
                              className="input"
                              type="number"
                              step="any"
                              style={{ maxWidth: 120 }}
                              value={requirement.target_value ?? ""}
                              onChange={(e) => updateRequirement(index, { target_value: Number(e.target.value) })}
                            />
                            <span className="badge">{requirement.target_unit}</span>
                          </div>
                        )}
                      </td>
                      <td>
                        <select
                          className="select"
                          value={requirement.hard_or_soft}
                          onChange={(e) => updateRequirement(index, { hard_or_soft: e.target.value })}
                        >
                          <option value="hard">hard</option>
                          <option value="soft">soft</option>
                        </select>
                      </td>
                      <td className="muted" style={{ maxWidth: 320 }}>{requirement.rationale}</td>
                    </tr>
                  ))}
                  {requirements.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <div className="empty">
                          No requirements yet. Pick an application template or enable the incumbent floors on
                          the previous step.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {create.error && <div className="notice fail">{(create.error as Error).message}</div>}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        <button className="btn btn-secondary" disabled={step === 1} onClick={() => setStep(step - 1)}>Back</button>
        {step < 3 ? (
          <button className="btn" disabled={step === 1 && !baseline} onClick={() => setStep(step + 1)}>Continue</button>
        ) : (
          <button
            className="btn"
            disabled={create.isPending || included.length === 0 || !baseline}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create study"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function NewStudyPage() {
  return (
    <Suspense fallback={<div className="empty">Loading…</div>}>
      <StudyWizard />
    </Suspense>
  );
}
