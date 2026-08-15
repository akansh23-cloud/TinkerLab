"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AxisOption, DecisionRequirement, PropertySpaceResponse } from "@/lib/decision";
import { AshbyChart } from "@/components/charts/AshbyChart";

/**
 * The property space with this study's own thresholds drawn on it.
 *
 * The shaded rectangle is the region that satisfies both axes' requirements, so the question stops
 * being "where does the incumbent sit" and becomes "what else is in the box". Only requirements
 * that bound the plotted axes are used — a thermal requirement cannot constrain a strength axis,
 * and drawing a box from unrelated thresholds would be a confident lie about the feasible set.
 */
export function ProjectPropertySpace({
  baselineId, requirements,
}: {
  baselineId: string;
  requirements: DecisionRequirement[];
}) {
  const [x, setX] = useState("density");
  const [y, setY] = useState("tensile_strength");
  const [indexKey, setIndexKey] = useState("");

  const axes = useQuery({
    queryKey: ["property-space-axes"],
    queryFn: () => api<AxisOption[]>("/bench/property-space/axes"),
  });
  const space = useQuery({
    queryKey: ["property-space", x, y, baselineId],
    queryFn: () => api<PropertySpaceResponse>(
      `/bench/property-space?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}&highlight=${baselineId}`,
    ),
  });

  /** Bounds for one axis, already converted by the API into that axis's canonical unit. */
  function windowFor(key: string): { min?: number; max?: number } | undefined {
    const relevant = requirements.filter((r) => r.property_key === key);
    if (!relevant.length) return undefined;
    const bounds: { min?: number; max?: number } = {};
    for (const requirement of relevant) {
      const value = requirement.canonical_target_value;
      const upper = requirement.canonical_target_value_upper;
      if (typeof value !== "number") continue;
      if (requirement.comparator === ">=" || requirement.comparator === ">") {
        bounds.min = bounds.min === undefined ? value : Math.max(bounds.min, value);
      } else if (requirement.comparator === "<=" || requirement.comparator === "<") {
        bounds.max = bounds.max === undefined ? value : Math.min(bounds.max, value);
      } else if (requirement.comparator === "between" && typeof upper === "number") {
        bounds.min = bounds.min === undefined ? value : Math.max(bounds.min, value);
        bounds.max = bounds.max === undefined ? upper : Math.min(bounds.max, upper);
      }
    }
    return bounds.min === undefined && bounds.max === undefined ? undefined : bounds;
  }

  const requirementX = windowFor(x);
  const requirementY = windowFor(y);
  const constrainedKeys = new Set(requirements.map((r) => r.property_key));

  return (
    <div className="grid">
      <div className="grid grid-3">
        <label className="label">
          X axis
          <select className="select" value={x} onChange={(e) => { setX(e.target.value); setIndexKey(""); }}>
            {axes.data?.map((a) => (
              <option key={a.key} value={a.key}>
                {a.display_name}{constrainedKeys.has(a.key) ? " ✓ constrained" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          Y axis
          <select className="select" value={y} onChange={(e) => { setY(e.target.value); setIndexKey(""); }}>
            {axes.data?.map((a) => (
              <option key={a.key} value={a.key}>
                {a.display_name}{constrainedKeys.has(a.key) ? " ✓ constrained" : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="label">
          Thresholds on these axes
          <div className="muted" style={{ marginTop: 6 }}>
            {requirementX || requirementY
              ? "The shaded box is the region that satisfies both."
              : "This study sets no numeric threshold on either axis, so no feasible region is drawn."}
          </div>
        </div>
      </div>

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
          requirementX={requirementX}
          requirementY={requirementY}
        />
      )}
    </div>
  );
}
