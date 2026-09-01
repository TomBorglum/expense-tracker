import { afterEach, expect, test, vi } from "vitest";

import { calendarBounds, currentYear, fromIsoDate, toIsoDate } from "@/dates";

afterEach(() => {
  vi.useRealTimers();
});

test("names the day the date is locally, not the day it is in UTC", () => {
  // Local midnight on the 1st. vite.config.ts pins the suite to a zone ahead of UTC, so
  // toISOString() would name July here - which is the whole point of the helper.
  const midnight = new Date(2026, 7, 1);
  expect(toIsoDate(midnight)).toBe("2026-08-01");
  expect(midnight.toISOString().slice(0, 10)).not.toBe("2026-08-01");
});

test("pads a month, a day and a year to their full width", () => {
  expect(toIsoDate(new Date(2026, 0, 2))).toBe("2026-01-02");
  expect(toIsoDate(new Date(999, 11, 31))).toBe("0999-12-31");
});

test("reads a YYYY-MM-DD string as local midnight", () => {
  const parsed = fromIsoDate("2026-08-01");
  expect(parsed?.getFullYear()).toBe(2026);
  expect(parsed?.getMonth()).toBe(7);
  expect(parsed?.getDate()).toBe(1);
  expect(parsed?.getHours()).toBe(0);
});

// The same values backend/tests/test_date_range.py refuses, so the two halves agree on
// what a date is. A trailing newline is caught by the round trip rather than the shape.
test.each(["", "yesterday", "20260102", "2026-W01-1", "02/01/2026", "2026-1-2"])(
  "refuses %j, which is not a date in YYYY-MM-DD form",
  (value) => {
    expect(fromIsoDate(value)).toBeUndefined();
  },
);

test.each(["2026-02-30", "2026-13-01", "2026-01-02\n"])(
  "refuses %j, which does not survive the round trip",
  (value) => {
    expect(fromIsoDate(value)).toBeUndefined();
  },
);

test("bounds the calendar at the first selectable year and the end of this one", () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 7, 20, 12, 0));
  const bounds = calendarBounds();
  expect(toIsoDate(bounds.start)).toBe("2025-01-01");
  expect(toIsoDate(bounds.end)).toBe("2026-12-31");
});

test("carries the upper bound forward with the year", () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2031, 2, 3));
  const bounds = calendarBounds();
  // The floor is fixed and the ceiling moves, so the dropdown grows by an entry a year.
  expect(toIsoDate(bounds.start)).toBe("2025-01-01");
  expect(toIsoDate(bounds.end)).toBe("2031-12-31");
});

test("spans the whole calendar year the clock is in", () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 6, 4, 12, 0));
  expect(currentYear()).toEqual({ from: "2026-01-01", to: "2026-12-31" });
});

test("names the year from the local clock and not through UTC", () => {
  // A minute past midnight on New Year's Day in Europe/Copenhagen is still the previous
  // year in UTC, so a currentYear built through toISOString would name 2025 here.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 0, 1, 0, 1));
  expect(currentYear().from).toBe("2026-01-01");
});
