import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { DateRangePicker } from "@/components/DateRangePicker";

// The day and nav buttons are named by react-day-picker's own labels - a day is
// format(date, "PPPP") under the default en-US locale, the nav pair is a fixed English
// string. A locale prop or a library bump moves them, and these queries are where that
// would show up.
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
  const grid = await screen.findByRole("grid");
  expect(grid.querySelectorAll("[data-selected]")).toHaveLength(0);
});
