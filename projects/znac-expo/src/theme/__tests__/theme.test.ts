import { describe, expect, it } from "vitest";

import {
  color,
  getMobileTheme,
  resolveSourceTheme,
  toReactNativeColor,
} from "../index";

describe("theme", () => {
  it("resolves @tokens references from znacpy json", () => {
    const theme = resolveSourceTheme("dark");

    expect(color(theme, "header.surface")).toBe("#24222b");
    expect(color(theme, "header.text")).toBe("#f4f1f8");
  });

  it("adds small mobile aliases and dark overrides", () => {
    const theme = getMobileTheme("dark");

    expect(theme.colors.primary).toBe("#8b5cf6");
    expect(theme.colors.text).toBe("#f4f1f8");
    expect(theme.row.validDay).toBe("#2a4938");
  });

  it("converts Qt alpha hex to React Native alpha hex", () => {
    expect(toReactNativeColor("#87000000")).toBe("#00000087");
  });
});
