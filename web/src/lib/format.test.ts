import { describe, expect, it } from "vitest";
import { formatCountdown, formatMetric, formatTerm, formatUsd } from "./format";

describe("formatTerm", () => {
  it("renders n/a when a term key is missing from the dict", () => {
    const terms = { cost: 10 };
    expect(formatTerm(terms, "latency")).toBe("n/a");
  });

  it("renders a present zero value as 0, not n/a", () => {
    const terms = { cost: 0 };
    expect(formatTerm(terms, "cost")).toBe("0");
  });

  it("renders a present non-zero value", () => {
    const terms = { cost: 42 };
    expect(formatTerm(terms, "cost")).toBe("42");
  });
});

describe("formatMetric / formatUsd", () => {
  it("renders 'no data' for null or undefined, never 0", () => {
    expect(formatMetric(null)).toBe("no data");
    expect(formatMetric(undefined)).toBe("no data");
    expect(formatUsd(null)).toBe("no data");
  });

  it("renders a present zero value as a real zero", () => {
    expect(formatMetric(0)).toBe("0");
    expect(formatUsd(0)).toBe("$0.00");
  });
});

describe("formatCountdown", () => {
  it("formats seconds as m:ss", () => {
    expect(formatCountdown(900)).toBe("15:00");
    expect(formatCountdown(65)).toBe("1:05");
    expect(formatCountdown(5)).toBe("0:05");
  });

  it("never goes negative", () => {
    expect(formatCountdown(-10)).toBe("0:00");
  });
});
