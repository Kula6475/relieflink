import { describe, expect, it } from "vitest";

import { shouldUseSyntheticMode } from "./vision";

describe("vision mode selection", () => {
  it("allows an explicit cloud request to override the synthetic demo default", () => {
    expect(shouldUseSyntheticMode("false", true)).toBe(false);
  });

  it("allows an explicit synthetic request to override the server default", () => {
    expect(shouldUseSyntheticMode("true", false)).toBe(true);
  });

  it("uses the server default when the client does not choose", () => {
    expect(shouldUseSyntheticMode(null, true)).toBe(true);
  });
});
