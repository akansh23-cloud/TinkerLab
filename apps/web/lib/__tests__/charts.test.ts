import { describe, expect, it } from "vitest";
import {
  clampMargin, familyColor, familyShape, formatValue, linearScale, logScale, logTicks,
  markerPath, niceTicks, originStyle, requirementMargin, statusColor,
} from "../charts";

describe("chart scales", () => {
  it("maps a linear domain onto a pixel range", () => {
    const s = linearScale(0, 100, 0, 500);
    expect(s(0)).toBe(0);
    expect(s(50)).toBe(250);
    expect(s(100)).toBe(500);
  });

  it("survives a degenerate domain instead of dividing by zero", () => {
    const s = linearScale(5, 5, 0, 100);
    expect(Number.isFinite(s(5))).toBe(true);
  });

  it("places decades evenly on a log scale", () => {
    const s = logScale(1, 1000, 0, 300);
    expect(s(1)).toBeCloseTo(0);
    expect(s(10)).toBeCloseTo(100);
    expect(s(100)).toBeCloseTo(200);
    expect(s(1000)).toBeCloseTo(300);
  });

  it("keeps polymer and ceramic moduli distinguishable, which a linear axis would not", () => {
    // Real case: polymer ~2 GPa against ceramic ~400 GPa. On a linear axis every polymer lands in
    // the same pixel column; on a log axis they separate. This is why the Ashby chart uses log axes.
    const linear = linearScale(2000, 400000, 0, 600);
    const log = logScale(2000, 400000, 0, 600);
    expect(Math.abs(linear(2000) - linear(3000))).toBeLessThan(2);
    expect(Math.abs(log(2000) - log(3000))).toBeGreaterThan(20);
  });
});

describe("ticks", () => {
  it("emits decade majors across a wide range", () => {
    const ticks = logTicks(1, 10000).filter((t) => t.major).map((t) => t.value);
    expect(ticks).toEqual([1, 10, 100, 1000, 10000]);
  });

  it("adds 2x and 5x minors when the range is narrow enough to need them", () => {
    const ticks = logTicks(1, 100);
    expect(ticks.some((t) => !t.major && t.value === 20)).toBe(true);
  });

  it("returns nothing for a non-positive domain rather than NaN ticks", () => {
    expect(logTicks(0, 100)).toEqual([]);
    expect(logTicks(-5, 5)).toEqual([]);
  });

  it("produces round linear ticks inside the domain", () => {
    const ticks = niceTicks(0, 100, 5);
    expect(ticks.length).toBeGreaterThan(2);
    expect(Math.min(...ticks)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ticks)).toBeLessThanOrEqual(100);
  });
});

describe("value formatting", () => {
  it("uses engineering suffixes", () => {
    expect(formatValue(1360)).toBe("1.36k");
    expect(formatValue(400000)).toBe("400k");
    expect(formatValue(0.22)).toBe("0.22");
  });

  it("renders a non-finite value as an em dash rather than NaN", () => {
    expect(formatValue(NaN)).toBe("—");
    expect(formatValue(Infinity)).toBe("—");
  });
});

describe("requirement margin", () => {
  it("signs a minimum requirement so positive means headroom", () => {
    // Requirement >= 145, observed 150 → 3.4% of headroom.
    expect(requirementMargin(150, 145, ">=")).toBeCloseTo(3.448, 2);
    expect(requirementMargin(130, 145, ">=")).toBeLessThan(0);
  });

  it("signs a maximum requirement the same way, so one axis reads consistently", () => {
    // Requirement <= 8.5, observed 7.0 → positive, because being under a ceiling is headroom.
    expect(requirementMargin(7.0, 8.5, "<=")).toBeGreaterThan(0);
    expect(requirementMargin(9.0, 8.5, "<=")).toBeLessThan(0);
  });

  it("returns null for an unmeasured value rather than zero", () => {
    // Zero would place the candidate exactly on the limit, asserting marginality where the truth
    // is an absence of evidence. This distinction is the whole point of tracking UNKNOWN.
    expect(requirementMargin(null, 145, ">=")).toBeNull();
    expect(requirementMargin(undefined, 145, ">=")).toBeNull();
  });

  it("returns null for a boolean gate, which has no percentage margin", () => {
    expect(requirementMargin(1, 1, "boolean")).toBeNull();
  });

  it("returns null against a zero threshold instead of dividing by it", () => {
    expect(requirementMargin(10, 0, ">=")).toBeNull();
  });

  it("clamps for drawing while remembering that it clipped", () => {
    expect(clampMargin(450)).toEqual({ value: 100, clipped: true });
    expect(clampMargin(-450)).toEqual({ value: -100, clipped: true });
    expect(clampMargin(42)).toEqual({ value: 42, clipped: false });
  });
});

describe("encoding meaning without relying on colour", () => {
  it("gives each family a distinct marker shape as well as a colour", () => {
    const families = ["polymer", "alloy", "ceramic", "composite", "coating"];
    const shapes = new Set(families.map(familyShape));
    // If shape were constant, a colour-blind reader would lose the family grouping entirely.
    expect(shapes.size).toBeGreaterThanOrEqual(4);
    expect(new Set(families.map(familyColor)).size).toBe(families.length);
  });

  it("falls back rather than returning undefined for an unseen family", () => {
    expect(familyColor("nanofoam")).toBeTruthy();
    expect(familyShape("nanofoam")).toBe("circle");
  });

  it("emits a valid path for every marker shape", () => {
    for (const shape of ["circle", "square", "triangle", "diamond", "cross", "pentagon", "hexagon", "x"] as const) {
      const path = markerPath(shape, 50, 50, 6);
      expect(path.startsWith("M")).toBe(true);
      expect(path).not.toContain("NaN");
    }
  });

  it("makes a prediction visually weaker than a measurement", () => {
    // Flattening this distinction in a chart would undo the platform's central claim in one image.
    expect(originStyle("measured").opacity).toBeGreaterThan(originStyle("prediction").opacity);
    expect(originStyle("prediction").dashed).toBe(true);
    expect(originStyle("measured").dashed).toBe(false);
  });

  it("separates pass, fail and unknown into three distinct colours", () => {
    const colors = new Set([statusColor("PASS"), statusColor("FAIL"), statusColor("UNKNOWN")]);
    expect(colors.size).toBe(3);
  });
});
