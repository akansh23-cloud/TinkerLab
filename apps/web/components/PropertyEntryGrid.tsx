"use client";
import { useMemo, useState } from "react";
import { CatalogueDomain, PropertySpec, directionLabel } from "@/lib/bench";

export type PropertyValue = {
  property_key: string;
  value?: number;
  boolean_value?: boolean;
  unit?: string;
  temperature_value?: number;
  method?: string;
  note?: string;
};

/**
 * Property entry grouped the way an engineer reads a datasheet, not the way the database stores it.
 *
 * Two decisions carry most of the value here. Every property shows its test standard and why it
 * matters, because a form that asks for "flexural modulus" without saying "ISO 178" is asking the
 * user to guess which of two non-interchangeable numbers on their datasheet to type. And a typed
 * value outside the handbook range for its family gets a warning inline, not a rejection — the
 * person entering a genuinely unusual number is the one you least want to block.
 */
export function PropertyEntryGrid({
  domains, family, values, onChange,
}: {
  domains: CatalogueDomain[];
  family: string;
  values: PropertyValue[];
  onChange: (next: PropertyValue[]) => void;
}) {
  const [openDomain, setOpenDomain] = useState<string>(domains[0]?.key ?? "");
  const [filter, setFilter] = useState("");

  const byKey = useMemo(() => new Map(values.map((v) => [v.property_key, v])), [values]);

  const visibleDomains = useMemo(() => {
    if (!filter.trim()) return domains;
    const needle = filter.trim().toLowerCase();
    return domains
      .map((d) => ({
        ...d,
        properties: d.properties.filter(
          (p) =>
            p.display_name.toLowerCase().includes(needle) ||
            p.key.includes(needle) ||
            p.datasheet_aliases.some((a) => a.includes(needle)),
        ),
      }))
      .filter((d) => d.properties.length > 0);
  }, [domains, filter]);

  function update(key: string, patch: Partial<PropertyValue>) {
    const existing = byKey.get(key);
    const next = existing
      ? values.map((v) => (v.property_key === key ? { ...v, ...patch } : v))
      : [...values, { property_key: key, ...patch }];
    onChange(next);
  }

  function clear(key: string) {
    onChange(values.filter((v) => v.property_key !== key));
  }

  function rangeWarning(spec: PropertySpec, raw: number | undefined): string | null {
    if (raw === undefined || Number.isNaN(raw)) return null;
    const window = spec.typical_range?.[family];
    if (!window || window.length < 2) return null;
    const [low, high] = window;
    if (raw >= low && raw <= high) return null;
    return `Outside the ${low}–${high} range typical for ${family} grades. Saved as entered — check the unit.`;
  }

  const filled = values.length;

  return (
    <div className="grid">
      <div className="topline" style={{ marginBottom: 0, alignItems: "center" }}>
        <div>
          <div className="eyebrow">Property data</div>
          <div className="muted">
            {filled} value{filled === 1 ? "" : "s"} entered. Record only what you have — a blank field stays
            UNKNOWN, which is a more useful answer than a guess.
          </div>
        </div>
        <input
          className="input"
          style={{ maxWidth: 260 }}
          placeholder="Find a property (try “UTS”)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      <div className="tabs" role="tablist">
        {visibleDomains.map((d) => {
          const count = d.properties.filter((p) => byKey.has(p.key)).length;
          return (
            <button
              key={d.key}
              type="button"
              role="tab"
              aria-selected={openDomain === d.key}
              className={`tab ${openDomain === d.key ? "active" : ""}`}
              onClick={() => setOpenDomain(d.key)}
            >
              {d.display_name}
              {count > 0 && <span className="badge pass" style={{ marginLeft: 6 }}>{count}</span>}
            </button>
          );
        })}
      </div>

      {visibleDomains
        .filter((d) => d.key === openDomain || filter.trim().length > 0)
        .map((domain) => (
          <div className="card" key={domain.key}>
            <div className="card-pad" style={{ paddingBottom: 10 }}>
              <h2>{domain.display_name}</h2>
              <p className="muted" style={{ margin: "4px 0 0" }}>{domain.description}</p>
            </div>
            <div className="prop-list">
              {domain.properties.map((spec) => {
                const current = byKey.get(spec.key);
                const isBoolean = spec.quantity_type === "boolean";
                const warning = isBoolean ? null : rangeWarning(spec, current?.value);
                return (
                  <div className={`prop-row ${current ? "prop-row-filled" : ""}`} key={spec.key}>
                    <div className="prop-meta">
                      <label className="prop-name" htmlFor={`prop-${spec.key}`}>{spec.display_name}</label>
                      <div className="prop-why">{spec.why_it_matters}</div>
                      <div className="prop-tags">
                        {spec.test_standard && <span className="badge">{spec.test_standard}</span>}
                        <span className="badge">{directionLabel(spec.direction)}</span>
                        {spec.condition_sensitive && (
                          <span className="badge unknown" title="Value is meaningless without its test condition">
                            Condition-sensitive
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="prop-input">
                      {isBoolean ? (
                        <select
                          id={`prop-${spec.key}`}
                          className="select"
                          value={current?.boolean_value === undefined ? "" : String(current.boolean_value)}
                          onChange={(e) =>
                            e.target.value === ""
                              ? clear(spec.key)
                              : update(spec.key, { boolean_value: e.target.value === "true" })
                          }
                        >
                          <option value="">Not recorded</option>
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      ) : (
                        <div className="prop-numeric">
                          <input
                            id={`prop-${spec.key}`}
                            className="input"
                            type="number"
                            step="any"
                            placeholder="—"
                            value={current?.value ?? ""}
                            onChange={(e) =>
                              e.target.value === ""
                                ? clear(spec.key)
                                : update(spec.key, {
                                    value: Number(e.target.value),
                                    unit: current?.unit ?? spec.accepted_units[0] ?? spec.canonical_unit ?? "",
                                  })
                            }
                          />
                          <select
                            className="select"
                            aria-label={`${spec.display_name} unit`}
                            value={current?.unit ?? spec.accepted_units[0] ?? ""}
                            onChange={(e) => update(spec.key, { unit: e.target.value })}
                          >
                            {spec.accepted_units.map((u) => (
                              <option key={u} value={u}>{u}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {spec.condition_sensitive && current && !isBoolean && (
                        <input
                          className="input"
                          type="number"
                          step="any"
                          placeholder="Test temperature °C (optional)"
                          value={current.temperature_value ?? ""}
                          onChange={(e) =>
                            update(spec.key, {
                              temperature_value: e.target.value === "" ? undefined : Number(e.target.value),
                            })
                          }
                        />
                      )}
                      {warning && <div className="prop-warn">{warning}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
    </div>
  );
}
