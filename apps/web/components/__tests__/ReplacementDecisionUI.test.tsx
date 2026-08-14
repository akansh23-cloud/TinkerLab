import {describe, expect, it} from "vitest";
import {render, screen} from "@testing-library/react";
import {MatrixCellBadge} from "@/components/MatrixCellBadge";
import {EvidenceGapBadge} from "@/components/EvidenceGapBadge";
import {ProgramStateBadge} from "@/components/ProgramStateBadge";
import {EligibilityBadge} from "@/components/EligibilityBadge";
import {ActionPriorityBadge} from "@/components/ActionPriorityBadge";
import {QualificationNotice} from "@/components/QualificationNotice";

describe("MatrixCellBadge", () => {
  it("renders UNKNOWN explicitly rather than as an empty cell", () => {
    render(<MatrixCellBadge status="unknown"/>);
    expect(screen.getByTestId("matrix-unknown")).toHaveTextContent("UNKNOWN — NO EVIDENCE");
  });

  it("never labels a non-failure status as a failure", () => {
    for (const status of ["unknown","inconclusive","not_comparable","conflicting"]) {
      const {unmount} = render(<MatrixCellBadge status={status}/>);
      expect(screen.getByTestId(`matrix-${status}`).textContent).not.toMatch(/FAIL/);
      unmount();
    }
  });

  it("distinguishes conflicting evidence from a pass", () => {
    render(<MatrixCellBadge status="conflicting"/>);
    expect(screen.getByTestId("matrix-conflicting")).toHaveTextContent("CONFLICTING EVIDENCE");
  });
});

describe("EvidenceGapBadge", () => {
  it("describes a blocking gap as outstanding work, not a rejection", () => {
    render(<EvidenceGapBadge gapClass="blocking_gap"/>);
    const badge = screen.getByTestId("gap-blocking_gap");
    expect(badge).toHaveTextContent("BLOCKING GAP");
    expect(badge.textContent).not.toMatch(/FAIL|REJECT/);
  });
});

describe("ProgramStateBadge", () => {
  it("marks operator-set states so they are not read as findings", () => {
    render(<ProgramStateBadge state="paused"/>);
    expect(screen.getByTestId("program-paused")).toHaveTextContent("SET BY OPERATOR");
  });

  it("renders the no-suitable-candidate state as a real outcome", () => {
    render(<ProgramStateBadge state="no_suitable_candidate"/>);
    expect(screen.getByTestId("program-no_suitable_candidate")).toHaveTextContent("NO SUITABLE CANDIDATE");
  });
});

describe("EligibilityBadge", () => {
  it("separates missing evidence from definitive failure", () => {
    const {unmount} = render(<EligibilityBadge eligibility="unresolved"/>);
    expect(screen.getByTestId("eligibility-unresolved")).toHaveTextContent("EVIDENCE OUTSTANDING");
    unmount();
    render(<EligibilityBadge eligibility="blocked"/>);
    expect(screen.getByTestId("eligibility-blocked")).toHaveTextContent("DEFINITIVE FAILURE");
  });
});

describe("ActionPriorityBadge", () => {
  it("shows the score and states that it is not a probability", () => {
    render(<ActionPriorityBadge priority={0.72} factors={{formula:"priority = a * b / c"}}/>);
    const badge = screen.getByTestId("priority-high");
    expect(badge).toHaveTextContent("PRIORITY 0.720");
    expect(badge.getAttribute("title")).toMatch(/not a probability/);
  });
});

describe("QualificationNotice", () => {
  it("always states that a recommendation is not a qualification decision", () => {
    render(<QualificationNotice/>);
    const notice = screen.getByTestId("qualification-notice");
    expect(notice).toHaveTextContent("Not a qualification decision");
    expect(notice.textContent).toMatch(/not authorization to replace the incumbent material/);
  });
});
