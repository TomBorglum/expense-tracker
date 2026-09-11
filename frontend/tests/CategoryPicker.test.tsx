import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CategoryPicker } from "@/components/CategoryPicker";

const OPTIONS = ["Car", "Groceries", "Housing", "Insurance"];

function trigger() {
  return screen.getByRole("button", { name: /^Categories / });
}

function checkbox(name: string) {
  return screen.getByRole<HTMLInputElement>("checkbox", { name });
}

function checkboxes() {
  return screen
    .queryAllByRole<HTMLInputElement>("checkbox")
    .map((box) => [box.labels?.[0]?.textContent, box.checked]);
}

function renderPicker(selected: string[], options = OPTIONS, disabled = false) {
  const onChange = vi.fn<(categories: string[]) => void>();
  render(
    <CategoryPicker
      selected={selected}
      options={options}
      disabled={disabled}
      onChange={onChange}
    />,
  );
  return onChange;
}

test("reads as every category when nothing is selected", () => {
  renderPicker([]);
  expect(trigger().textContent).toBe("All categories");
});

test("names one or two selected categories and counts three", () => {
  renderPicker(["Car"]);
  expect(trigger().textContent).toBe("Car");
});

test("names two", () => {
  renderPicker(["Car", "Housing"]);
  expect(trigger().textContent).toBe("Car, Housing");
});

test("counts three, so a long selection cannot wrap the filter row", () => {
  renderPicker(["Car", "Groceries", "Housing"]);
  expect(trigger().textContent).toBe("3 categories");
});

test("keeps the list out of the document until it is opened", async () => {
  renderPicker(["Car"]);
  expect(screen.queryByRole("group")).toBeNull();

  await userEvent.click(trigger());

  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
  expect(
    screen.getByRole("button", { name: /^Categories /, expanded: true }),
  ).toBeTruthy();
  // One box per option, in the order given, ticked where the selection says so.
  expect(checkboxes()).toEqual([
    ["Car", true],
    ["Groceries", false],
    ["Housing", false],
    ["Insurance", false],
  ]);
});

test("reports the selection in option order, whatever order it was ticked in", async () => {
  // One selection is one URL: ticking Housing then Car spells the same as Car then
  // Housing.
  const onChange = renderPicker(["Housing"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([[["Car", "Housing"]]]);
});

test("reports the selection without a category that was unticked", async () => {
  const onChange = renderPicker(["Car", "Housing"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([[["Housing"]]]);
});

test("stays open after a tick, so several can be picked in a row", async () => {
  renderPicker(["Car"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Housing"));
  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
});

test("offers to clear the selection only while there is one", async () => {
  renderPicker([]);
  await userEvent.click(trigger());
  expect(screen.queryByRole("button", { name: "Clear selection" })).toBeNull();
});

test("clears the whole selection in one click", async () => {
  const onChange = renderPicker(["Car", "Housing"]);
  await userEvent.click(trigger());
  await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(onChange.mock.calls).toEqual([[[]]]);
});

test("closes when a click lands outside it", async () => {
  renderPicker([]);
  await userEvent.click(trigger());
  screen.getByRole("group", { name: "Categories" });

  await userEvent.click(document.body);

  expect(screen.queryByRole("group")).toBeNull();
});

test("closes on Escape and hands focus back to the trigger", async () => {
  renderPicker([]);
  await userEvent.click(trigger());
  screen.getByRole("group", { name: "Categories" });

  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("group")).toBeNull();
  expect(document.activeElement).toBe(trigger());
});

test("closes again on a second click of the trigger", async () => {
  renderPicker([]);
  await userEvent.click(trigger());
  await userEvent.click(trigger());
  expect(screen.queryByRole("group")).toBeNull();
});

test("can be worked from the keyboard", async () => {
  // Tab reaches the first box from the trigger and Space ticks it: the disclosure
  // pattern leaves focus on the trigger when it opens.
  const onChange = renderPicker([]);
  await userEvent.click(trigger());
  await userEvent.tab();
  expect(document.activeElement).toBe(checkbox("Car"));
  await userEvent.keyboard(" ");
  expect(onChange.mock.calls).toEqual([[["Car"]]]);
});

test("is disabled when told to be", async () => {
  renderPicker([], [], true);
  expect(trigger().hasAttribute("disabled")).toBe(true);
  await userEvent.click(trigger());
  expect(screen.queryByRole("group")).toBeNull();
});

test("shows a category nobody offered rather than silently dropping it", async () => {
  // Reachable by typing a name into the address bar: the URL is passed to the backend
  // unchecked, so the control has to agree with the request that is in flight.
  renderPicker(["Travel"], ["Car", "Housing"]);
  expect(trigger().textContent).toBe("Travel");
  await userEvent.click(trigger());
  expect(checkboxes()).toEqual([
    ["Travel", true],
    ["Car", false],
    ["Housing", false],
  ]);
});
