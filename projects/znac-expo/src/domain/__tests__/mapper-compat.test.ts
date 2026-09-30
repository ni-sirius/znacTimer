import { describe, expect, it } from "vitest";

import { minuteText, parseClock } from "../time";

describe("repository mapper compatibility", () => {
  it("test_unset_and_midnight_have_distinct_round_trips", () => {
    expect(minuteText(null)).toBe("--:--");
    expect(parseClock(minuteText(null))).toBeNull();

    expect(minuteText(0)).toBe("00:00");
    expect(parseClock(minuteText(0))).toBe(0);
  });

  it("test_blank_and_placeholder_both_clear_a_clock", () => {
    expect(parseClock("")).toBeNull();
    expect(parseClock("--:--")).toBeNull();
  });
});
