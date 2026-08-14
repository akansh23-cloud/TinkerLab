import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {SimulationWarning} from "../SimulationWarning";
import {RouteStatusBadge} from "../RouteStatusBadge";
import {ConvergenceBadge} from "../ConvergenceBadge";

describe("Phase 6 simulation disclosure components", () => {
  it("states that simulation is not physical validation", () => {
    render(<SimulationWarning/>);
    const text = screen.getByTestId("simulation-warning").textContent ?? "";
    expect(text).toMatch(/not a physical experiment/i);
    expect(text).toMatch(/three separate scientific origins/i);
  });

  it("renders refusal statuses as explicit labels, never as a silent blank", () => {
    render(<RouteStatusBadge status="missing_registered_artifact"/>);
    expect(screen.getByText("MISSING REGISTERED ARTIFACT")).toBeTruthy();
  });

  it("keeps an unknown status visible rather than hiding it", () => {
    render(<RouteStatusBadge status="some_future_status"/>);
    expect(screen.getByText("SOME_FUTURE_STATUS")).toBeTruthy();
  });

  it("never shows an unconverged run as an accepted value", () => {
    render(<ConvergenceBadge status="unconverged"/>);
    expect(screen.getByText(/NO ACCEPTED VALUE/)).toBeTruthy();
  });

  it("labels a missing result rather than implying success", () => {
    render(<ConvergenceBadge/>);
    expect(screen.getByText("NO RESULT")).toBeTruthy();
  });
});
