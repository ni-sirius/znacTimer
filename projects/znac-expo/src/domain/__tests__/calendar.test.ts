import { describe, expect, it } from "vitest";

import {
  buildCalendarWeekText,
  calendarWeekTagDisplay,
  isWeekendDisplay,
} from "../calendar";

describe("calendar utils parity", () => {
  it("test_is_weekend", () => {
    expect(isWeekendDisplay("15.06.2024")).toBe(true);
    expect(isWeekendDisplay("17.06.2024")).toBe(false);
  });

  it("test_calendar_week_tag", () => {
    expect(calendarWeekTagDisplay("17.06.2024")).toBe("CW-25");
  });

  it("test_build_calendar_week_text", () => {
    expect(buildCalendarWeekText(2024, 6, "2024-06-17")).toBe(
      "Calendar week 25, This month 22-26, This year 52",
    );
  });
});
