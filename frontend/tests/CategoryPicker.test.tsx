import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { type Category } from "@/api/categories";
import { CategoryPicker } from "@/components/CategoryPicker";

// Three roots and one path below the first, deliberately not in an order a pre-order
// walk could be mistaken for: Car2024 sorts between Car and Car:Fuel under the byte
// order the backend lists in, so a picker reading the list as contiguous would nest it.
const OPTIONS: Category[] = [
  { category: "Car", name: "Car" },
  { category: "Car2024", name: "Car2024" },
  { category: "Car:Fuel", name: "Fuel", parent: "Car" },
  { category: "Groceries", name: "Groceries" },
];

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

function indents() {
  return screen
    .queryAllByRole<HTMLInputElement>("checkbox")
    .map((box) => [
      box.labels?.[0]?.textContent,
      [...(box.labels?.[0]?.classList ?? [])].find((name) => name.startsWith("pl-")),
    ]);
}

function renderPicker(
  selected: string[],
  options: Category[] = OPTIONS,
  disabled = false,
) {
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

test("names one selected category", () => {
  renderPicker(["Car:Fuel"]);
  expect(trigger().textContent).toBe("Car:Fuel");
});

test("counts two, so a pair of paths cannot wrap the filter row", () => {
  // Two is already a count where two flat names were not: a pair of paths is longer
  // than the trigger's own width shows.
  renderPicker(["Car:Fuel", "Groceries"]);
  expect(trigger().textContent).toBe("2 categories");
});

test("keeps the list out of the document until it is opened", async () => {
  renderPicker(["Car"]);
  expect(screen.queryByRole("group")).toBeNull();

  await userEvent.click(trigger());

  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
  expect(
    screen.getByRole("button", { name: /^Categories /, expanded: true }),
  ).toBeTruthy();
  // One box per option, in walk order rather than the order given, labelled by its own
  // level and ticked where the selection says so.
  expect(checkboxes()).toEqual([
    ["Car", true],
    ["Fuel", false],
    ["Car2024", false],
    ["Groceries", false],
  ]);
});

test("renders a child under its parent rather than where the list put it", async () => {
  // Built from `parent`, not from list order: Car2024 arrives between Car and Car:Fuel
  // and still sits at the root, which is what a contiguity walk would get wrong.
  renderPicker([]);
  await userEvent.click(trigger());
  expect(indents()).toEqual([
    ["Car", "pl-0"],
    ["Fuel", "pl-4"],
    ["Car2024", "pl-0"],
    ["Groceries", "pl-0"],
  ]);
});

test("reports a child by its whole path, not by the level it shows", async () => {
  const onChange = renderPicker([]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Fuel"));
  expect(onChange.mock.calls).toEqual([[["Car:Fuel"]]]);
});

test("ticks a parent without touching its children", async () => {
  // The backend already reads a node as its whole subtree, so auto-ticking would be
  // redundant - and a parent beside its own child is a request in its own right.
  const onChange = renderPicker([]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([[["Car"]]]);
  expect(checkbox("Fuel").checked).toBe(false);
});

test("reports the selection in option order, whatever order it was ticked in", async () => {
  // One selection is one URL: ticking Housing then Car spells the same as Car then
  // Housing.
  const onChange = renderPicker(["Groceries"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([[["Car", "Groceries"]]]);
});

test("reports the selection without a category that was unticked", async () => {
  const onChange = renderPicker(["Car", "Groceries"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([[["Groceries"]]]);
});

test("stays open after a tick, so several can be picked in a row", async () => {
  renderPicker(["Car"]);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Groceries"));
  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
});

test("keeps the clear button in place, disabled, while there is nothing to clear", async () => {
  // Present rather than absent, so the panel is the same size whatever is ticked.
  renderPicker([]);
  await userEvent.click(trigger());
  const clear = screen.getByRole<HTMLButtonElement>("button", {
    name: "Clear selection",
  });
  expect(clear.disabled).toBe(true);
});

test("clears the whole selection in one click", async () => {
  const onChange = renderPicker(["Car", "Groceries"]);
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
  // A path, because that is what the address bar carries: it has no parent in the tree
  // to sit under, so it is labelled in full and listed flat, ahead of the rest.
  renderPicker(
    ["Travel:Spain"],
    [
      { category: "Car", name: "Car" },
      { category: "Groceries", name: "Groceries" },
    ],
  );
  expect(trigger().textContent).toBe("Travel:Spain");
  await userEvent.click(trigger());
  expect(indents()).toEqual([
    ["Travel:Spain", "pl-0"],
    ["Car", "pl-0"],
    ["Groceries", "pl-0"],
  ]);
});
