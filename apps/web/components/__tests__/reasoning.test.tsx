import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {RequirementStatusBadge} from "../RequirementStatusBadge";
import {OriginBadge} from "../OriginBadge";

describe("Phase 8 reasoning disclosure components", () => {
  it("never lets UNKNOWN look like a pass", () => {
    render(<RequirementStatusBadge status="unknown"/>);
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
  });

  it("names a state mismatch rather than calling it missing data", () => {
    render(<RequirementStatusBadge status="state_mismatch"/>);
    expect(screen.getByText("WRONG MATERIAL STATE")).toBeTruthy();
  });

  it("shows conflicting evidence as its own outcome", () => {
    render(<RequirementStatusBadge status="conflicting_evidence"/>);
    expect(screen.getByText("CONFLICTING EVIDENCE")).toBeTruthy();
  });

  it("keeps a prediction visually distinct from a measurement", () => {
    const {unmount} = render(<OriginBadge origin="predicted"/>);
    expect(screen.getByText("PREDICTED")).toBeTruthy();
    unmount();
    render(<OriginBadge origin="observed"/>);
    expect(screen.getByText("OBSERVED")).toBeTruthy();
  });

  it("labels simulation as simulation, not experiment", () => {
    render(<OriginBadge origin="simulated"/>);
    expect(screen.getByText("SIMULATED")).toBeTruthy();
    expect(screen.queryByText("EXPERIMENTAL")).toBeNull();
  });

  it("renders an unrecognised status visibly instead of hiding it", () => {
    render(<RequirementStatusBadge status="some_future_status"/>);
    expect(screen.getByText("SOME_FUTURE_STATUS")).toBeTruthy();
  });
});
