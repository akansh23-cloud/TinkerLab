import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {IndustrialStateBadge} from "../IndustrialStateBadge";
import {IndustrialSeparationNotice} from "../IndustrialSeparationNotice";
import {EvidenceQualifiers} from "../EvidenceQualifiers";
import type {IndustrialEvidence} from "@/lib/api";

const evidence = (over: Partial<IndustrialEvidence> = {}): IndustrialEvidence => ({
  id:"e1", category:"economic", metric_key:"raw_material_cost", display_label:"cost",
  numeric_value:28, unit:"USD/kg", currency:"USD", currency_year:2025, cost_basis:"per_kilogram",
  geography:"global", as_of_date:"2025-03-01", conditions:{}, source_type:"seed_demonstration",
  is_estimate:false, scientific_origin:"industrial_evidence", content_checksum:"abc", status:"active",
  created_at:"2025-03-01T00:00:00Z", ...over,
});

describe("Phase 7 industrial disclosure components", () => {
  it("renders an absent answer as loudly as a verdict", () => {
    render(<IndustrialStateBadge state="insufficient_evidence"/>);
    expect(screen.getByText("INSUFFICIENT EVIDENCE")).toBeTruthy();
  });

  it("never renders unknown as blank", () => {
    render(<IndustrialStateBadge state="unknown"/>);
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
  });

  it("surfaces contradiction as its own state rather than a pass", () => {
    render(<IndustrialStateBadge state="conflicting_evidence"/>);
    expect(screen.getByText("CONFLICTING EVIDENCE")).toBeTruthy();
  });

  it("states that industrial evidence is a separate claim class", () => {
    render(<IndustrialSeparationNotice/>);
    const text = screen.getByTestId("industrial-separation").textContent ?? "";
    expect(text).toMatch(/never become property observations/i);
  });

  it("always shows the qualifiers that make a cost figure comparable", () => {
    render(<EvidenceQualifiers evidence={evidence()}/>);
    const text = screen.getByTestId("evidence-qualifiers").textContent ?? "";
    expect(text).toContain("USD");
    expect(text).toContain("2025");
    expect(text).toContain("per_kilogram");
    expect(text).toContain("as of 2025-03-01");
  });

  it("calls out a missing as-of date instead of hiding it", () => {
    render(<EvidenceQualifiers evidence={evidence({as_of_date: undefined})}/>);
    expect(screen.getByTestId("evidence-qualifiers").textContent).toContain("NO AS-OF DATE");
  });

  it("marks an estimate as an estimate", () => {
    render(<EvidenceQualifiers evidence={evidence({is_estimate: true})}/>);
    expect(screen.getByTestId("evidence-qualifiers").textContent).toContain("ESTIMATE");
  });
});
