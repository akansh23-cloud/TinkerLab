import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  it.each(["PASS", "FAIL", "UNKNOWN"])("renders explicit %s label", status => {
    render(<StatusBadge status={status}/>);
    expect(screen.getByText(status)).toBeInTheDocument();
  });
});
