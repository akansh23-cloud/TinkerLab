"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, MaterialDetailV2 } from "@/lib/api";
import { DataGrade, IntakeWarning, PropertyCatalogue } from "@/lib/bench";
import { PropertyEntryGrid, PropertyValue } from "@/components/PropertyEntryGrid";

export default function AddMaterialDataPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const material = useQuery({
    queryKey: ["material", id],
    queryFn: () => api<MaterialDetailV2>(`/materials/${id}`),
  });
  const catalogue = useQuery({
    queryKey: ["property-catalogue"],
    queryFn: () => api<PropertyCatalogue>("/bench/property-catalogue"),
  });
  const grades = useQuery({
    queryKey: ["data-grades"],
    queryFn: () => api<DataGrade[]>("/bench/data-grades"),
  });

  const [dataGrade, setDataGrade] = useState("internal_measurement");
  const [sourceReference, setSourceReference] = useState("");
  const [method, setMethod] = useState("");
  const [note, setNote] = useState("");
  const [properties, setProperties] = useState<PropertyValue[]>([]);
  const [saved, setSaved] = useState<{ count: number; warnings: IntakeWarning[] } | null>(null);

  const selectedGrade = grades.data?.find((g) => g.key === dataGrade);
  const referenceMissing = Boolean(selectedGrade?.requires_reference) && sourceReference.trim().length === 0;

  const submit = useMutation({
    mutationFn: () =>
      api<{ observation_count: number; warnings: IntakeWarning[] }>(`/bench/materials/${id}/properties`, {
        method: "POST",
        body: JSON.stringify({
          data_grade: dataGrade,
          source_reference: sourceReference.trim() || null,
          method: method.trim() || null,
          note: note.trim() || null,
          properties: properties.map((p) => ({
            property_key: p.property_key,
            value: p.value ?? null,
            boolean_value: p.boolean_value ?? null,
            unit: p.unit ?? null,
            temperature_value: p.temperature_value ?? null,
          })),
        }),
      }),
    onSuccess: (data) => {
      setSaved({ count: data.observation_count, warnings: data.warnings });
      setProperties([]);
      material.refetch();
    },
  });

  if (material.isLoading) return <div className="empty">Loading material…</div>;
  if (material.error || !material.data) {
    return <div className="empty">Material unavailable: {(material.error as Error)?.message}</div>;
  }

  const existingKeys = new Set(material.data.observations.map((o) => o.property_definition.key));

  return (
    <div className="grid">
      <div className="topline">
        <div>
          <div className="eyebrow">Add property data</div>
          <h1>{material.data.display_name}</h1>
          <div className="muted">
            {existingKeys.size} propert{existingKeys.size === 1 ? "y" : "ies"} already recorded across{" "}
            {material.data.observations.length} observation(s). New values are added alongside, never over the top.
          </div>
        </div>
        <Link className="btn btn-secondary" href={`/materials/${id}`}>Back to material</Link>
      </div>

      {saved && (
        <div className="notice pass">
          <strong>Recorded {saved.count} value{saved.count === 1 ? "" : "s"}.</strong>
          <div>
            Where a new value disagrees with an existing one, both are kept and the conflict is reported on the
            material record.
          </div>
          {saved.warnings.map((w) => (
            <div className="muted" key={w.property_key}>{w.property_key}: {w.message}</div>
          ))}
        </div>
      )}

      <div className="card card-pad">
        <div className="eyebrow">Provenance</div>
        <h2>Where is this batch of data from?</h2>
        <div className="grid" style={{ marginTop: 14 }}>
          {grades.data?.map((grade) => (
            <label key={grade.key} className={`grade-option ${dataGrade === grade.key ? "grade-selected" : ""}`}>
              <input
                type="radio"
                name="append-grade"
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
            <input className="input" value={sourceReference} onChange={(e) => setSourceReference(e.target.value)} />
          </label>
          <label className="label">
            Test method or conditions
            <input
              className="input"
              placeholder="ISO 527, 5 specimens, 23 °C"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            />
          </label>
        </div>
        <label className="label" style={{ marginTop: 14 }}>
          Curator note <span className="muted">(optional)</span>
          <textarea className="textarea" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>

      <div className="card card-pad">
        {catalogue.data && (
          <PropertyEntryGrid
            domains={catalogue.data.domains}
            family={material.data.material_family}
            values={properties}
            onChange={setProperties}
          />
        )}
      </div>

      <div className="card card-pad">
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <button
            className="btn"
            disabled={properties.length === 0 || referenceMissing || submit.isPending}
            onClick={() => submit.mutate()}
          >
            {submit.isPending ? "Saving…" : `Record ${properties.length || ""} value${properties.length === 1 ? "" : "s"}`}
          </button>
          {referenceMissing && <span className="muted">This grade needs a source reference.</span>}
        </div>
        {submit.error && <div className="notice fail" style={{ marginTop: 12 }}>{(submit.error as Error).message}</div>}
      </div>
    </div>
  );
}
