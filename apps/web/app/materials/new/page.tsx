"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  COMPONENT_ROLES, DataGrade, FAMILY_OPTIONS, IntakeResponse, PropertyCatalogue,
} from "@/lib/bench";
import { PropertyEntryGrid, PropertyValue } from "@/components/PropertyEntryGrid";

type ComponentDraft = {
  component_name: string;
  component_role: string;
  amount_value: string;
  amount_unit: string;
  is_redacted: boolean;
};

const EMPTY_COMPONENT: ComponentDraft = {
  component_name: "", component_role: "matrix", amount_value: "", amount_unit: "%", is_redacted: false,
};

export default function MaterialIntakePage() {
  const catalogue = useQuery({
    queryKey: ["property-catalogue"],
    queryFn: () => api<PropertyCatalogue>("/bench/property-catalogue"),
  });
  const grades = useQuery({
    queryKey: ["data-grades"],
    queryFn: () => api<DataGrade[]>("/bench/data-grades"),
  });

  const [displayName, setDisplayName] = useState("");
  const [family, setFamily] = useState<string>("polymer");
  const [supplier, setSupplier] = useState("");
  const [gradeCode, setGradeCode] = useState("");
  const [description, setDescription] = useState("");
  const [dataGrade, setDataGrade] = useState("supplier_datasheet");
  const [sourceReference, setSourceReference] = useState("");
  const [method, setMethod] = useState("");
  const [note, setNote] = useState("");
  const [processState, setProcessState] = useState("");
  const [components, setComponents] = useState<ComponentDraft[]>([
    { ...EMPTY_COMPONENT },
    { ...EMPTY_COMPONENT, component_role: "reinforcement", amount_unit: "%" },
  ]);
  const [properties, setProperties] = useState<PropertyValue[]>([]);
  const [result, setResult] = useState<IntakeResponse | null>(null);

  const selectedGrade = grades.data?.find((g) => g.key === dataGrade);
  const componentTotal = useMemo(
    () => components.reduce((sum, c) => sum + (Number(c.amount_value) || 0), 0),
    [components],
  );
  const namedComponents = components.filter((c) => c.component_name.trim().length > 0);

  const referenceMissing = Boolean(selectedGrade?.requires_reference) && sourceReference.trim().length === 0;
  const canSubmit =
    displayName.trim().length >= 2 && !referenceMissing && properties.length > 0;

  const submit = useMutation({
    mutationFn: () =>
      api<IntakeResponse>("/bench/materials", {
        method: "POST",
        body: JSON.stringify({
          display_name: displayName.trim(),
          material_family: family,
          data_grade: dataGrade,
          description: description.trim() || null,
          supplier: supplier.trim() || null,
          grade_code: gradeCode.trim() || null,
          source_reference: sourceReference.trim() || null,
          method: method.trim() || null,
          note: note.trim() || null,
          components: namedComponents.map((c) => ({
            component_name: c.component_name.trim(),
            component_role: c.component_role,
            amount_value: c.amount_value === "" ? null : Number(c.amount_value),
            amount_unit: c.amount_unit,
            amount_basis: "weight_percent",
            is_redacted: c.is_redacted,
            redaction_label: c.is_redacted ? "Withheld by supplier" : null,
          })),
          process_state: processState.trim() ? { state_label: processState.trim() } : null,
          properties: properties.map((p) => ({
            property_key: p.property_key,
            value: p.value ?? null,
            boolean_value: p.boolean_value ?? null,
            unit: p.unit ?? null,
            temperature_value: p.temperature_value ?? null,
            method: p.method ?? null,
            note: p.note ?? null,
          })),
        }),
      }),
    onSuccess: setResult,
  });

  function updateComponent(index: number, patch: Partial<ComponentDraft>) {
    setComponents(components.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  if (result) {
    return (
      <div className="grid">
        <div className="topline">
          <div>
            <div className="eyebrow">Material recorded</div>
            <h1>{result.display_name}</h1>
            <div className="muted">
              {result.observation_count} propert{result.observation_count === 1 ? "y" : "ies"} recorded under one
              evidence record, graded <strong>{selectedGrade?.display_name ?? result.data_grade}</strong>.
            </div>
          </div>
        </div>

        {result.warnings.length > 0 && (
          <div className="notice">
            <strong>Saved as entered, with {result.warnings.length} value{result.warnings.length === 1 ? "" : "s"} to double-check</strong>
            {result.warnings.map((w) => (
              <div className="muted" key={w.property_key}>{w.property_key}: {w.message}</div>
            ))}
          </div>
        )}

        <div className="card card-pad">
          <h2>What next</h2>
          <div className="grid grid-3" style={{ marginTop: 14 }}>
            <Link className="btn" href={`/studies/new?baseline=${result.material_id}`}>
              Start a replacement study
            </Link>
            <Link className="btn btn-secondary" href={`/materials/${result.material_id}`}>
              View the material record
            </Link>
            <Link className="btn btn-secondary" href={`/materials/${result.material_id}/add-data`}>
              Add more property data
            </Link>
          </div>
          <p className="muted" style={{ marginTop: 14 }}>
            Adding data from a second source later does not overwrite this one. Both are kept and the
            disagreement is reported — that difference is usually the most decision-relevant thing in the record.
          </p>
        </div>

        <button className="btn btn-secondary" onClick={() => { setResult(null); setProperties([]); setDisplayName(""); }}>
          Record another material
        </button>
      </div>
    );
  }

  return (
    <div className="grid">
      <div className="topline">
        <div>
          <div className="eyebrow">Material intake</div>
          <h1>Record a material</h1>
          <div className="muted">
            Transcribe a datasheet, a test report or your own measurements. Identity, composition and
            properties are saved together under one evidence record.
          </div>
        </div>
        <Link className="btn btn-secondary" href="/materials">Back to explorer</Link>
      </div>

      <div className="card card-pad">
        <div className="eyebrow">1 · Identity</div>
        <h2>What is this material?</h2>
        <div className="grid grid-2" style={{ marginTop: 14 }}>
          <label className="label">
            Name
            <input
              className="input"
              placeholder="PA66-GF30"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </label>
          <label className="label">
            Family
            <select className="select" value={family} onChange={(e) => setFamily(e.target.value)}>
              {FAMILY_OPTIONS.map((f) => <option key={f} value={f}>{f.replaceAll("_", " ")}</option>)}
            </select>
          </label>
          <label className="label">
            Supplier <span className="muted">(optional)</span>
            <input className="input" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
          </label>
          <label className="label">
            Grade code <span className="muted">(optional)</span>
            <input
              className="input"
              placeholder="A3WG6"
              value={gradeCode}
              onChange={(e) => setGradeCode(e.target.value)}
            />
          </label>
        </div>
        <label className="label" style={{ marginTop: 14 }}>
          Description <span className="muted">(optional)</span>
          <textarea className="textarea" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <p className="muted" style={{ marginTop: 10 }}>
          Supplier and grade code are combined with the name to keep two different suppliers’ PA66-GF30
          from colliding as one material.
        </p>
      </div>

      <div className="card card-pad">
        <div className="eyebrow">2 · Provenance</div>
        <h2>Where did these numbers come from?</h2>
        <p className="muted" style={{ margin: "6px 0 0" }}>
          This sets the confidence and evidence type on everything you record below. It cannot be raised
          later by editing a field, because the strength of a number is a property of its source.
        </p>
        <div className="grid" style={{ marginTop: 14 }}>
          {grades.data?.map((grade) => (
            <label
              key={grade.key}
              className={`grade-option ${dataGrade === grade.key ? "grade-selected" : ""}`}
            >
              <input
                type="radio"
                name="data-grade"
                checked={dataGrade === grade.key}
                onChange={() => setDataGrade(grade.key)}
              />
              <span>
                <strong>{grade.display_name}</strong>
                <span className="badge" style={{ marginLeft: 8 }}>confidence {grade.confidence}</span>
                <div className="muted">{grade.description}</div>
              </span>
            </label>
          ))}
        </div>
        <div className="grid grid-2" style={{ marginTop: 14 }}>
          <label className="label">
            Source reference {selectedGrade?.requires_reference && <span className="badge fail">Required</span>}
            <input
              className="input"
              placeholder="Datasheet rev C, 2026-01 / Report LAB-2291"
              value={sourceReference}
              onChange={(e) => setSourceReference(e.target.value)}
            />
          </label>
          <label className="label">
            Test method or conditions <span className="muted">(optional)</span>
            <input
              className="input"
              placeholder="ISO 527, 23 °C, dry as moulded"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            />
          </label>
        </div>
        {referenceMissing && (
          <div className="notice fail" style={{ marginTop: 12 }}>
            The <strong>{selectedGrade?.display_name}</strong> grade claims external authority, so it needs a
            reference someone can check — a report number, datasheet revision or citation.
          </div>
        )}
        <label className="label" style={{ marginTop: 14 }}>
          Curator note <span className="muted">(optional)</span>
          <textarea
            className="textarea"
            rows={2}
            placeholder="Values are dry-as-moulded; conditioned modulus not supplied."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
      </div>

      <div className="card card-pad">
        <div className="eyebrow">3 · Composition</div>
        <h2>What is it made of?</h2>
        <p className="muted" style={{ margin: "6px 0 0" }}>
          Optional, but composition is what candidate generation varies. Without at least a matrix and one
          additive with numeric amounts, no search space can be derived and the Candidate Lab stays closed.
        </p>
        <div className="table-wrap" style={{ marginTop: 14 }}>
          <table>
            <thead>
              <tr><th>Component</th><th>Role</th><th>Amount</th><th>Unit</th><th>Withheld</th><th /></tr>
            </thead>
            <tbody>
              {components.map((component, index) => (
                <tr key={index}>
                  <td>
                    <input
                      className="input"
                      placeholder="Polyamide 66"
                      value={component.component_name}
                      onChange={(e) => updateComponent(index, { component_name: e.target.value })}
                    />
                  </td>
                  <td>
                    <select
                      className="select"
                      value={component.component_role}
                      onChange={(e) => updateComponent(index, { component_role: e.target.value })}
                    >
                      {COMPONENT_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td>
                    <input
                      className="input"
                      type="number"
                      step="any"
                      value={component.amount_value}
                      onChange={(e) => updateComponent(index, { amount_value: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="input"
                      style={{ maxWidth: 90 }}
                      value={component.amount_unit}
                      onChange={(e) => updateComponent(index, { amount_unit: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label="Amount withheld by supplier"
                      checked={component.is_redacted}
                      onChange={(e) => updateComponent(index, { is_redacted: e.target.checked })}
                    />
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setComponents(components.filter((_, i) => i !== index))}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <button className="btn btn-secondary" onClick={() => setComponents([...components, { ...EMPTY_COMPONENT, component_role: "additive" }])}>
            Add component
          </button>
          <div className="muted">
            Total {componentTotal.toFixed(2)}
            {Math.abs(componentTotal - 100) > 0.5 && namedComponents.length > 0 && (
              <span className="badge unknown" style={{ marginLeft: 8 }}>Does not sum to 100</span>
            )}
          </div>
        </div>
        <label className="label" style={{ marginTop: 14 }}>
          Process state <span className="muted">(optional)</span>
          <input
            className="input"
            placeholder="Injection moulded, dry as moulded / T6 aged"
            value={processState}
            onChange={(e) => setProcessState(e.target.value)}
          />
        </label>
      </div>

      <div className="card card-pad">
        <div className="eyebrow">4 · Properties</div>
        {catalogue.isLoading && <div className="empty">Loading the property catalogue…</div>}
        {catalogue.data && (
          <PropertyEntryGrid
            domains={catalogue.data.domains}
            family={family}
            values={properties}
            onChange={setProperties}
          />
        )}
      </div>

      <div className="card card-pad">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn" disabled={!canSubmit || submit.isPending} onClick={() => submit.mutate()}>
            {submit.isPending ? "Saving…" : "Save material"}
          </button>
          <span className="muted">
            {properties.length === 0
              ? "Record at least one property value."
              : `${properties.length} propert${properties.length === 1 ? "y" : "ies"} ready to save.`}
          </span>
        </div>
        {submit.error && <div className="notice fail" style={{ marginTop: 12 }}>{(submit.error as Error).message}</div>}
      </div>
    </div>
  );
}
