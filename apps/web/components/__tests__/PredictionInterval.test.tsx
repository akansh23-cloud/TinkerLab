import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PredictionInterval } from "../PredictionInterval";
describe("PredictionInterval",()=>{it("renders point and uncertainty interval",()=>{render(<PredictionInterval point={76} lower={68} upper={84} unit="MPa"/>);expect(screen.getByText(/76.00 MPa/)).toBeInTheDocument();expect(screen.getByText(/68.00–84.00 MPa/)).toBeInTheDocument();});it("does not fabricate a number",()=>{render(<PredictionInterval/>);expect(screen.getByText(/No numeric prediction/i)).toBeInTheDocument();});});
