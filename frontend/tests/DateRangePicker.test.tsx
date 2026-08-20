import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DateRangePicker } from "@/components/DateRangePicker";

// The day and nav buttons are named by react-day-picker's own labels - a day is
// format(date, "PPPP") under the default en-US locale, the nav pair is a fixed English
// string. A locale prop or a library bump moves them, and these queries are where that
// would show up.
// The calendar falls back to the current month when the URL carries no readable start,
// and calendarBounds() reads the clock for its upper year, so both are pinned here.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 7, 20, 12, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

function trigger() {
  return screen.getByRole("button", { name: /^Dates / });
}

function day(name: string) {
  return screen.getByRole("button", { name: new RegExp(name) });
}

function renderPicker(from: string, to: string) {
  const onChange = vi.fn<(from: string, to: string) => void>();
  render(<DateRangePicker from={from} to={to} onChange={onChange} />);
  return onChange;
}

test("shows the two dates it was given, verbatim", () => {
  renderPicker("2026-08-01", "2026-08-31");
  expect(trigger().textContent).toBe("2026-08-01 to 2026-08-31");
});

test("keeps the calendar out of the document until it is opened", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  expect(screen.queryByRole("grid")).toBeNull();

  await userEvent.click(trigger());

  expect(await screen.findByRole("grid", { name: "August 2026" })).toBeTruthy();
  expect(screen.getByRole("button", { name: /^Dates /, expanded: true })).toBeTruthy();
});

test("opens on the month the range starts in, not on the current one", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  expect(await screen.findByRole("grid", { name: "March 2026" })).toBeTruthy();
});

test("reports a range only once both of its ends are picked", async () => {
  const onChange = renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());

  await userEvent.click(day("August 3rd, 2026"));
  // A start on its own would be an open-ended range, and the backend reads an empty
  // bound as malformed rather than as no bound.
  expect(onChange).not.toHaveBeenCalled();

  await userEvent.click(day("August 10th, 2026"));
  expect(onChange.mock.calls).toEqual([["2026-08-03", "2026-08-10"]]);
});

test("closes once it has reported a range", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await userEvent.click(day("August 3rd, 2026"));
  await userEvent.click(day("August 10th, 2026"));
  expect(screen.queryByRole("grid")).toBeNull();
});

test("cannot be made to report a range that runs backwards", async () => {
  // The second click lands before the first. react-day-picker orders the pair itself,
  // which is why nothing here compares them.
  const onChange = renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await userEvent.click(day("August 20th, 2026"));
  await userEvent.click(day("August 4th, 2026"));
  expect(onChange.mock.calls).toEqual([["2026-08-04", "2026-08-20"]]);
});

test("reports a single day when both ends are the same", async () => {
  // Both bounds are inclusive on the backend, so one day is a range and not a refusal.
  const onChange = renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await userEvent.click(day("August 7th, 2026"));
  await userEvent.click(day("August 7th, 2026"));
  expect(onChange.mock.calls).toEqual([["2026-08-07", "2026-08-07"]]);
});

test("clicking the only day of a one-day range reports nothing", async () => {
  // react-day-picker clears the selection outright here. There is no half range to hold
  // and nothing to report, so the URL keeps the range it already had.
  const onChange = renderPicker("2026-08-07", "2026-08-07");
  await userEvent.click(trigger());
  await userEvent.click(day("August 7th, 2026"));
  expect(onChange).not.toHaveBeenCalled();
  expect(trigger().textContent).toBe("2026-08-07 to 2026-08-07");
});

test("walks to another month and picks there", async () => {
  const onChange = renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await userEvent.click(
    screen.getByRole("button", { name: "Go to the Previous Month" }),
  );

  expect(await screen.findByRole("grid", { name: "July 2026" })).toBeTruthy();
  await userEvent.click(day("July 6th, 2026"));
  await userEvent.click(day("July 9th, 2026"));
  expect(onChange.mock.calls).toEqual([["2026-07-06", "2026-07-09"]]);
});

test("shows a date nobody could parse rather than correcting it", async () => {
  // validateSearch hands the URL on as typed, so the control agrees with the request in
  // flight even when that request is going to be refused.
  renderPicker("yesterday", "2026-08-31");
  expect(trigger().textContent).toBe("yesterday to 2026-08-31");

  await userEvent.click(trigger());
  // The end still reads as a date and is still marked; the start highlights nothing
  // rather than being guessed at.
  const grid = await screen.findByRole("grid", { name: "August 2026" });
  expect(
    [...grid.querySelectorAll("[data-selected]")].map((td) =>
      td.getAttribute("data-day"),
    ),
  ).toEqual(["2026-08-31"]);
});

test("highlights nothing at all when neither end reads as a date", async () => {
  renderPicker("yesterday", "tomorrow");
  await userEvent.click(trigger());
  await screen.findByRole("grid", { name: "August 2026" });
  expect(document.querySelectorAll("[data-selected]")).toHaveLength(0);
});

test("shows two months at once, the second following the first", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  const months = await screen.findAllByRole("grid");
  expect(months.map((grid) => grid.getAttribute("aria-label"))).toEqual([
    "March 2026",
    "April 2026",
  ]);
});

test("offers every year from the first selectable one to the current, newest first", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  // One caption, and so one pair of dropdowns, per month on show.
  const [years] = await screen.findAllByRole("combobox", { name: "Choose the Year" });
  expect(
    [...years.querySelectorAll("option")].map((option) => option.textContent),
  ).toEqual(["2026", "2025"]);
});

test("jumps to a month chosen from the dropdown", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  const [month] = await screen.findAllByRole("combobox", { name: "Choose the Month" });

  await userEvent.selectOptions(month, "10");

  expect(await screen.findByRole("grid", { name: "November 2026" })).toBeTruthy();
});

test("jumps to a year chosen from the dropdown", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  const [year] = await screen.findAllByRole("combobox", { name: "Choose the Year" });

  await userEvent.selectOptions(year, "2025");

  expect(await screen.findByRole("grid", { name: "March 2025" })).toBeTruthy();
});

test("will not walk back past the first selectable month", async () => {
  // The bound exists to give the year dropdown a finite list, and it clamps the arrows
  // with it. An expense dated earlier is only reachable by typing the URL.
  renderPicker("2025-01-05", "2025-01-09");
  await userEvent.click(trigger());
  const previous = await screen.findByRole("button", {
    name: "Go to the Previous Month",
  });
  expect(previous.getAttribute("aria-disabled")).toBe("true");
});

test("will not walk forward past the end of the current year", async () => {
  renderPicker("2026-12-05", "2026-12-09");
  await userEvent.click(trigger());
  const next = await screen.findByRole("button", { name: "Go to the Next Month" });
  expect(next.getAttribute("aria-disabled")).toBe("true");
});
