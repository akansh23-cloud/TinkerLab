"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AxisOption, IndexRanking, PropertySpaceResponse } from "@/lib/decision";
import { AshbyChart } from "@/components/charts/AshbyChart";
import { familyColor, formatValue } from "@/lib/charts";
import { FAMILY_OPTIONS } from "@/lib/bench";

function Explorer() {
  const [x, setX] = useState("density");
  const [y, setY] = useState("tensile_strength");
  const [family, setFamily] = useState("");
  const [indexKey, setIndexKey] = useState("");

  const axes = useQuery({
    queryKey: ["property-space-axes"],
    queryFn: () => api<AxisOption[]>("/bench/property-space/axes"),
  });
  const space = useQuery({
    queryKey: ["property-space", x, y, family],
    queryFn: () => api<PropertySpaceResponse>(
      `/bench/property-space?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}${family ? `&family=${family}` : ""}`,
    ),
  });
  const ranking = useQuery({
    queryKey: ["property-space-ranking", x, y, indexKey, family],
    enabled: Boolean(indexKey),
    queryFn: () => api<IndexRanking>(
      `/bench/property-space/ranking?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&index_key=${encodeURIComponent(indexKey)}${family ? `&family=${family}` : ""}`,
    ),
  });

  return (
    <div className="grid">
      <div className="topline">
        <div>
          <div className="eyebrow">Property space</div>
          <h1>Material selection chart</h1>
          <div className="muted">
            Two properties on logarithmic axes, materials by family. Pick a material index to see which
            material wins for a given loading mode rather than on a raw property.
          </div>
        </div>
        <Link className="btn btn-secondary" href="/materials">Materials explorer</Link>
      </div>

      <div className="card card-pad">
        <div className="grid grid-3">
          <label className="label">
            X axis
            <select className="select" value={x} onChange={(e) => { setX(e.target.value); setIndexKey(""); }}>
              {axes.data?.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.display_name} ({a.material_count})
                </option>
              ))}
            </select>
          </label>
          <label className="label">
            Y axis
            <select className="select" value={y} onChange={(e) => { setY(e.target.value); setIndexKey(""); }}>
              {axes.data?.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.display_name} ({a.material_count})
                </option>
              ))}
            </select>
          </label>
          <label className="label">
            Family
            <select className="select" value={family} onChange={(e) => setFamily(e.target.value)}>
              <option value="">All families</option>
              {FAMILY_OPTIONS.map((f) => <option key={f} value={f}>{f.replaceAll("_", " ")}</option>)}
            </select>
          </label>
        </div>
        {space.data && (
          <p className="muted" style={{ marginTop: 12 }}>
            {space.data.y_axis.why_it_matters}
          </p>
        )}
      </div>

      <div className="card card-pad">
        {space.isLoading && <div className="empty">Building the property space…</div>}
        {space.error && <div className="empty">{(space.error as Error).message}</div>}
        {space.data && (
          <AshbyChart
            points={space.data.points}
            xAxis={space.data.x_axis}
            yAxis={space.data.y_axis}
            indices={space.data.material_indices}
            activeIndexKey={indexKey}
            onSelectIndex={setIndexKey}
          />
        )}
      </div>

      {ranking.data && (
        <div className="card">
          <div className="card-pad">
            <div className="eyebrow">Ranked on {ranking.data.index.label}</div>
            <h2>{ranking.data.index.design_case}</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              This is the order that matters for this loading mode — which is not, in general, the order
              you would get by sorting on {ranking.data.y_axis.display_name.toLowerCase()} alone.
            </p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th><th>Material</th><th>Family</th>
                  <th>{ranking.data.index.label}</th>
                  <th>{ranking.data.x_axis.display_name}</th>
                  <th>{ranking.data.y_axis.display_name}</th>
                  <th>Weakest origin</th>
                </tr>
              </thead>
              <tbody>
                {ranking.data.ranking.slice(0, 15).map((row, i) => (
                  <tr key={row.material_id}>
                    <td>{i + 1}</td>
                    <td>
                      <Link href={`/materials/${row.material_id}`}><strong>{row.display_name}</strong></Link>
                    </td>
                    <td>
                      <span className="badge" style={{ borderColor: familyColor(row.material_family) }}>
                        {row.material_family}
                      </span>
                    </td>
                    <td><strong>{formatValue(row.index_value)}</strong></td>
                    <td>{formatValue(row.x)} {ranking.data.x_axis.canonical_unit}</td>
                    <td>{formatValue(row.y)} {ranking.data.y_axis.canonical_unit}</td>
                    <td className="muted">{row.lowest_origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {space.data && space.data.excluded.length > 0 && (
        <div className="card card-pad">
          <div className="eyebrow">Not plotted</div>
          <h2>{space.data.excluded_count} material(s) are absent from this chart</h2>
          <p className="muted" style={{ marginTop: 6 }}>
            A missing value is not a zero and is not a low score. These materials are named rather than
            quietly dropped, because “we have never measured this” is itself a finding.
          </p>
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>Material</th><th>Why</th><th /></tr></thead>
              <tbody>
                {space.data.excluded.slice(0, 20).map((row) => (
                  <tr key={row.material_id}>
                    <td>{row.display_name}</td>
                    <td className="muted">{row.reason}</td>
                    <td>
                      <Link className="btn btn-secondary btn-sm" href={`/materials/${row.material_id}/add-data`}>
                        Add the data
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PropertySpacePage() {
  return (
    <Suspense fallback={<div className="empty">Loading…</div>}>
      <Explorer />
    </Suspense>
  );
}
