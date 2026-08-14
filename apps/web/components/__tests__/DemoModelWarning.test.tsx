import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DemoModelWarning } from "../DemoModelWarning";
describe("DemoModelWarning",()=>{it("makes synthetic validation status explicit",()=>{render(<DemoModelWarning text="DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions."/>);expect(screen.getAllByText(/DEMO MODEL/).length).toBeGreaterThan(0);expect(screen.getByText(/Do not use.*real material decisions/i)).toBeInTheDocument();});});
