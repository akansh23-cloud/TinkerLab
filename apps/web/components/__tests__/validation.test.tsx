import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {ValidationStateBadge} from "../ValidationStateBadge";
import {MeasurementQualityBadge} from "../MeasurementQualityBadge";

describe("Phase 9 validation disclosure components", () => {
  it("never calls simulation support validation", () => {
    render(<ValidationStateBadge state="simulation_supported"/>);
    const text = screen.getByTestId("validation-simulation_supported").textContent ?? "";
    expect(text).toContain("NOT VALIDATED");
  });

  it("names a contradiction rather than softening it", () => {
    render(<ValidationStateBadge state="contradicted"/>);
    expect(screen.getByText(/CONTRADICTED BY MEASUREMENT/)).toBeTruthy();
  });

  it("says when measurements conflict instead of picking one", () => {
    render(<ValidationStateBadge state="inconclusive"/>);
    expect(screen.getByText(/MEASUREMENTS CONFLICT/)).toBeTruthy();
  });

  it("marks an untraceable measurement as not evidence", () => {
    render(<MeasurementQualityBadge quality="incomplete_provenance"/>);
    expect(screen.getByText(/NOT EVIDENCE/)).toBeTruthy();
  });

  it("distinguishes provisional from accepted", () => {
    const {unmount} = render(<MeasurementQualityBadge quality="provisional"/>);
    expect(screen.getByText("PROVISIONAL")).toBeTruthy();
    unmount();
    render(<MeasurementQualityBadge quality="accepted"/>);
    expect(screen.getByText("ACCEPTED")).toBeTruthy();
  });
});
