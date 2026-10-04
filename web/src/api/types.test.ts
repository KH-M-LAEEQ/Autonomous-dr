import { describe, expect, it } from "vitest";
import { riskLevelFor } from "./types";

describe("riskLevelFor", () => {
  it("is low below 0.33", () => {
    expect(riskLevelFor(0)).toBe("low");
    expect(riskLevelFor(0.32)).toBe("low");
  });

  it("is elevated from 0.33 up to (but not including) 0.66", () => {
    expect(riskLevelFor(0.33)).toBe("elevated");
    expect(riskLevelFor(0.5)).toBe("elevated");
    expect(riskLevelFor(0.65)).toBe("elevated");
  });

  it("is high at or above 0.66", () => {
    expect(riskLevelFor(0.66)).toBe("high");
    expect(riskLevelFor(1)).toBe("high");
  });
});
