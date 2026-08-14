import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PredictionOriginBadge } from "../PredictionOriginBadge";
describe("PredictionOriginBadge",()=>{it("distinguishes model predictions from evidence",()=>{const {rerender}=render(<PredictionOriginBadge origin="model_prediction"/>);expect(screen.getByText(/MODEL PREDICTION/)).toBeInTheDocument();rerender(<PredictionOriginBadge origin="known_evidence"/>);expect(screen.getByText(/KNOWN EVIDENCE/)).toBeInTheDocument();});});
