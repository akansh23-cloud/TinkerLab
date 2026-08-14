import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HypothesisWarning } from "../HypothesisWarning";
describe("HypothesisWarning",()=>{it("states the Phase-4 scientific boundary without a fake score",()=>{render(<HypothesisWarning/>);expect(screen.getByText(/not a validated or experimentally confirmed material/i)).toBeInTheDocument();expect(screen.getByText(/predictions.*separate estimates/i)).toBeInTheDocument();expect(screen.queryByText(/AI score/i)).not.toBeInTheDocument();});});
