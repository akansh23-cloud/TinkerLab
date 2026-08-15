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
    render(<ValidationStateBadge state="conflicting_experiments"/>);
    expect(screen.getByText(/CONFLICTING EXPERIMENTS/)).toBeTruthy();
  });

  // These two states are not synonyms and must not be rendered as if they were. "Inconclusive"
  // means the evidence does not settle the question; "conflicting experiments" means measurements
  // actively disagree. Labelling the former as a conflict would assert a disagreement that was
  // never observed — the same class of overstatement the badge exists to prevent.
  it("does not describe insufficient evidence as a conflict", () => {
    render(<ValidationStateBadge state="inconclusive"/>);
    const text = screen.getByTestId("validation-inconclusive").textContent ?? "";
    expect(text).toBe("INCONCLUSIVE");
    expect(text).not.toContain("CONFLICT");
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
