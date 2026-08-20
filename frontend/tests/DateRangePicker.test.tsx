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

async function shownMonths() {
  const grids = await screen.findAllByRole("grid");
  return grids.map((grid) => grid.getAttribute("aria-label"));
}

async function monthDropdown(panel: number) {
  const all = await screen.findAllByRole("combobox", { name: "Choose the Month" });
  return all[panel];
}

async function yearDropdown(panel: number) {
  const all = await screen.findAllByRole("combobox", { name: "Choose the Year" });
  return all[panel];
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

test("opens with a panel on each end of the range it was given", async () => {
  renderPicker("2026-01-05", "2026-04-28");
  await userEvent.click(trigger());
  expect(await shownMonths()).toEqual(["January 2026", "April 2026"]);
});

test("puts the right panel on the following month when the range sits in one", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());
  expect(await shownMonths()).toEqual(["March 2026", "April 2026"]);
});

test("returns to the range in the props each time it is opened", async () => {
  renderPicker("2026-01-05", "2026-04-28");
  await userEvent.click(trigger());
  await userEvent.selectOptions(await monthDropdown(0), "10");
  await userEvent.click(trigger());

  await userEvent.click(trigger());

  expect(await shownMonths()).toEqual(["January 2026", "April 2026"]);
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

test("jumps one panel to a month chosen from its dropdown", async () => {
  renderPicker("2026-03-05", "2026-03-09");
  await userEvent.click(trigger());

  await userEvent.selectOptions(await monthDropdown(1), "11");

  expect(await shownMonths()).toEqual(["March 2026", "December 2026"]);
});

test("changing the right year leaves the left where it is", async () => {
  // The two used to move as one, so the left could not be left on 2025 while the right
  // showed 2026.
  renderPicker("2025-03-05", "2025-03-09");
  await userEvent.click(trigger());

  await userEvent.selectOptions(await yearDropdown(1), "2026");

  expect(await shownMonths()).toEqual(["March 2025", "April 2026"]);
});

test("changing the left month leaves the right where it is", async () => {
  renderPicker("2026-01-05", "2026-06-09");
  await userEvent.click(trigger());

  await userEvent.selectOptions(await monthDropdown(0), "2");

  expect(await shownMonths()).toEqual(["March 2026", "June 2026"]);
});

test("moving the left panel past the right takes the right with it", async () => {
  renderPicker("2025-01-05", "2025-01-09");
  await userEvent.click(trigger());

  await userEvent.selectOptions(await yearDropdown(0), "2026");
  await userEvent.selectOptions(await monthDropdown(0), "11");

  // The panel that moved wins, and the other follows only as far as it must.
  expect(await shownMonths()).toEqual(["December 2026", "December 2026"]);
});

test("moving the right panel back past the left takes the left with it", async () => {
  renderPicker("2026-06-05", "2026-06-09");
  await userEvent.click(trigger());

  await userEvent.selectOptions(await yearDropdown(1), "2025");

  expect(await shownMonths()).toEqual(["July 2025", "July 2025"]);
});

test("offers no arrows, the dropdowns being the whole of the navigation", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await screen.findAllByRole("grid");
  expect(screen.queryByRole("button", { name: /Go to the .+ Month/ })).toBeNull();
});

test("closes when a click lands outside it", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await screen.findAllByRole("grid");

  await userEvent.click(document.body);

  expect(screen.queryByRole("grid")).toBeNull();
});

test("stays open for a click inside it", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  const [month] = await screen.findAllByRole("combobox", { name: "Choose the Month" });

  await userEvent.click(month);

  expect(screen.queryAllByRole("grid")).toHaveLength(2);
});

test("closes on Escape and hands focus back to the trigger", async () => {
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await screen.findAllByRole("grid");

  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("grid")).toBeNull();
  expect(document.activeElement).toBe(trigger());
});

test("discards a half-picked range when it is dismissed", async () => {
  // The URL still holds the range that was there, and a calendar disagreeing with the
  // trigger is worse than losing one click.
  const onChange = renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await userEvent.click(day("August 12th, 2026"));

  await userEvent.click(document.body);
  await userEvent.click(trigger());

  expect(onChange).not.toHaveBeenCalled();
  // Deduplicated: the last days of August also appear as outside days at the head of
  // the September panel, and are marked there too.
  const marked = [...document.querySelectorAll("[data-selected]")].map((cell) =>
    cell.getAttribute("data-day"),
  );
  const days = [...new Set(marked)].sort((a, b) => (a ?? "").localeCompare(b ?? ""));
  expect(days).toHaveLength(31);
  expect(days.at(0)).toBe("2026-08-01");
  expect(days.at(-1)).toBe("2026-08-31");
});

test("opens at the floor when the range starts before the first selectable month", async () => {
  // The URL is still honoured - the trigger shows it and the request carries it - but
  // the calendar cannot go there, so it opens as close as it can.
  renderPicker("2024-05-01", "2024-05-31");
  expect(trigger().textContent).toBe("2024-05-01 to 2024-05-31");

  await userEvent.click(trigger());

  expect(await shownMonths()).toEqual(["January 2025", "February 2025"]);
});

test("shows the ceiling month twice when there is nothing after it", async () => {
  renderPicker("2026-12-05", "2026-12-09");
  await userEvent.click(trigger());
  expect(await shownMonths()).toEqual(["December 2026", "December 2026"]);
});

test("ignores a key that is not Escape", async () => {
  // ArrowDown rather than Enter: focus is on the trigger after opening, and Enter would
  // activate it and close the panel by the ordinary toggle.
  renderPicker("2026-08-01", "2026-08-31");
  await userEvent.click(trigger());
  await screen.findAllByRole("grid");

  await userEvent.keyboard("{ArrowDown}");

  expect(screen.queryAllByRole("grid")).toHaveLength(2);
});
