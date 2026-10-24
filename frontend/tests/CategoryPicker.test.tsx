import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { type Category } from "@/api/categories";
import { type CategorySelection, EVERYTHING, NOTHING } from "@/categorySelection";
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

// Everything but one path below a root, which is the state the whole control exists for.
const WITHOUT_FUEL: CategorySelection = {
  root: true,
  selected: [],
  deselected: ["Car:Fuel"],
};

function trigger() {
  return screen.getByRole("button", { name: /^Categories / });
}

function checkbox(name: string) {
  return screen.getByRole<HTMLInputElement>("checkbox", { name });
}

// A node's disclosure button, named by the verb it would perform - so the query says
// both which node and which way it is currently open.
function twisty(verb: "Collapse" | "Expand", name: string) {
  return screen.getByRole<HTMLButtonElement>("button", { name: `${verb} ${name}` });
}

function twisties() {
  return screen
    .queryAllByRole("button", { name: /^(Collapse|Expand) / })
    .map((button) => button.getAttribute("aria-label"));
}

function checkboxes() {
  return screen
    .queryAllByRole<HTMLInputElement>("checkbox")
    .map((box) => [box.labels?.[0]?.textContent, box.checked]);
}

// The third state, which is a DOM property rather than an attribute, so it is read off
// the element rather than queried for.
function marks() {
  return screen
    .queryAllByRole<HTMLInputElement>("checkbox")
    .map((box) => [box.labels?.[0]?.textContent, box.indeterminate]);
}

// The indent sits on the row rather than on the label: the twisty is outside the label,
// so the two share a row element that carries the depth.
function indents() {
  return screen
    .queryAllByRole<HTMLInputElement>("checkbox")
    .map((box) => [
      box.labels?.[0]?.textContent,
      [...(box.labels?.[0]?.parentElement?.classList ?? [])].find((name) =>
        name.startsWith("pl-"),
      ),
    ]);
}

function renderPicker(
  selection: CategorySelection = EVERYTHING,
  options: Category[] = OPTIONS,
  disabled = false,
) {
  const onChange = vi.fn<(selection: CategorySelection) => void>();
  render(
    <CategoryPicker
      selection={selection}
      options={options}
      disabled={disabled}
      onChange={onChange}
    />,
  );
  return onChange;
}

function button(name: string) {
  return screen.getByRole<HTMLButtonElement>("button", { name });
}

test("reads as every category by default", () => {
  renderPicker();
  expect(trigger().textContent).toBe("All categories");
});

test("reads as no categories when the selection is empty", () => {
  // Distinct from the default, which is the whole point: the two were one state before.
  renderPicker(NOTHING);
  expect(trigger().textContent).toBe("No categories");
});

test("names the one category that is missing", () => {
  renderPicker(WITHOUT_FUEL);
  expect(trigger().textContent).toBe("All but Car:Fuel");
});

test("counts what is missing once naming it would not fit", () => {
  renderPicker({ root: true, selected: [], deselected: ["Car:Fuel", "Groceries"] });
  expect(trigger().textContent).toBe("All but 2");
});

test("names one picked category", () => {
  renderPicker({ root: false, selected: ["Car:Fuel"], deselected: [] });
  expect(trigger().textContent).toBe("Car:Fuel");
});

test("counts two, so a pair of paths cannot wrap the filter row", () => {
  // Two is already a count where two flat names were not: a pair of paths is longer
  // than the trigger's own width shows.
  renderPicker({ root: false, selected: ["Car:Fuel", "Groceries"], deselected: [] });
  expect(trigger().textContent).toBe("2 categories");
});

test("keeps the list out of the document until it is opened", async () => {
  renderPicker();
  expect(screen.queryByRole("group")).toBeNull();

  await userEvent.click(trigger());

  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
  expect(
    screen.getByRole("button", { name: /^Categories /, expanded: true }),
  ).toBeTruthy();
  // One box per option at the roots, in walk order rather than the order given, and
  // every one of them ticked: the default selects every category there is, which is
  // what makes deselecting a single one possible. Fuel is not among them - the panel
  // opens at the roots, and nothing below Car departs from Car's own sign.
  expect(checkboxes()).toEqual([
    ["Car", true],
    ["Car2024", true],
    ["Groceries", true],
  ]);
});

test("clears every box when the selection is empty", async () => {
  renderPicker(NOTHING);
  await userEvent.click(trigger());
  expect(checkboxes()).toEqual([
    ["Car", false],
    ["Car2024", false],
    ["Groceries", false],
  ]);
});

test("shows a branch on its twisty, and hides it again", async () => {
  renderPicker();
  await userEvent.click(trigger());
  expect(screen.queryByRole("checkbox", { name: "Fuel" })).toBeNull();

  await userEvent.click(twisty("Expand", "Car"));

  expect(checkbox("Fuel")).toBeTruthy();
  expect(twisty("Collapse", "Car").getAttribute("aria-expanded")).toBe("true");

  await userEvent.click(twisty("Collapse", "Car"));

  expect(screen.queryByRole("checkbox", { name: "Fuel" })).toBeNull();
});

test("offers a twisty only where there are children to disclose", async () => {
  // Car is the one option with any; a leaf keeps the width and offers no control.
  renderPicker();
  await userEvent.click(trigger());
  expect(twisties()).toEqual(["Expand Car"]);
});

test("opens the branch a flipped category sits in", async () => {
  // Otherwise the trigger would read "All but Car:Fuel" over a list with everything
  // ticked in it, and there would be no way to put Fuel back.
  renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  expect(checkboxes()).toEqual([
    ["Car", true],
    ["Fuel", false],
    ["Car2024", true],
    ["Groceries", true],
  ]);
});

test("marks a parent whose subtree disagrees with it", async () => {
  // The third state: Car is selected and Fuel is not, so a plain tick would say the
  // whole branch is in and a plain empty box would say none of it is.
  renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  expect(marks()).toEqual([
    ["Car", true],
    ["Fuel", false],
    ["Car2024", false],
    ["Groceries", false],
  ]);
});

test("leaves the mark off a parent its whole subtree agrees with", async () => {
  renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(twisty("Expand", "Car"));
  expect(marks()).toEqual([
    ["Car", false],
    ["Fuel", false],
    ["Car2024", false],
    ["Groceries", false],
  ]);
});

test("lets the parent of a flipped category be collapsed again", async () => {
  // What the map of clicks buys over a set of open paths: a set would hold this branch
  // open for as long as the selection lasted, and the twisty would do nothing.
  renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());

  await userEvent.click(twisty("Collapse", "Car"));

  expect(screen.queryByRole("checkbox", { name: "Fuel" })).toBeNull();
  expect(twisty("Expand", "Car")).toBeTruthy();
});

test("keeps a branch expanded across a close and a reopen", async () => {
  renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(twisty("Expand", "Car"));

  await userEvent.keyboard("{Escape}");
  await userEvent.click(trigger());

  expect(checkbox("Fuel")).toBeTruthy();
});

test("renders a child under its parent rather than where the list put it", async () => {
  // Built from `parent`, not from list order: Car2024 arrives between Car and Car:Fuel
  // and still sits at the root, which is what a contiguity walk would get wrong.
  renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(twisty("Expand", "Car"));
  expect(indents()).toEqual([
    ["Car", "pl-0"],
    ["Fuel", "pl-4"],
    ["Car2024", "pl-0"],
    ["Groceries", "pl-0"],
  ]);
});

test("reports one flip rather than one entry per category left", async () => {
  // The URL cost of deselecting one thing: one value, whatever the tree's size - and
  // the root stays selected, so a category imported later is in it too.
  const onChange = renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([
    [{ root: true, selected: [], deselected: ["Car"] }],
  ]);
});

test("reports a child by its whole path, not by the level it shows", async () => {
  const onChange = renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(twisty("Expand", "Car"));
  await userEvent.click(checkbox("Fuel"));
  expect(onChange.mock.calls).toEqual([[WITHOUT_FUEL]]);
});

test("unticking a parent takes the flips below it with it", async () => {
  // The cascade: the child's own flip would outlive its parent and keep part of the
  // subtree ticked, which is not what unticking a branch looks like.
  const onChange = renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([
    [{ root: true, selected: [], deselected: ["Car"] }],
  ]);
});

test("shows a child as unticked because its parent is", async () => {
  // The other half of the cascade, which is a reading rather than a stored flip: Fuel
  // carries no value of its own here and still answers for the branch it sits in.
  renderPicker({ root: true, selected: [], deselected: ["Car"] });
  await userEvent.click(trigger());
  await userEvent.click(twisty("Expand", "Car"));
  expect(checkboxes()).toEqual([
    ["Car", false],
    ["Fuel", false],
    ["Car2024", true],
    ["Groceries", true],
  ]);
});

test("keeps a child ticked that was put back inside an unticked parent", async () => {
  // The longest flip decides, so the two keys together say "everything except Car, but
  // keep its Fuel" - and the box the user has to see to believe that is Fuel's.
  renderPicker({ root: true, selected: ["Car:Fuel"], deselected: ["Car"] });
  await userEvent.click(trigger());
  expect(checkboxes()).toEqual([
    ["Car", false],
    ["Fuel", true],
    ["Car2024", true],
    ["Groceries", true],
  ]);
});

test("reports a flip in row order, whatever order the boxes were clicked in", async () => {
  // One selection is one URL: unticking Groceries then Car spells the same as the other
  // way round.
  const onChange = renderPicker({
    root: true,
    selected: [],
    deselected: ["Groceries"],
  });
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Car"));
  expect(onChange.mock.calls).toEqual([
    [{ root: true, selected: [], deselected: ["Car", "Groceries"] }],
  ]);
});

test("reports a flip inside a collapsed branch rather than dropping it", async () => {
  // The order the selection is reported in comes from the whole tree, not from the rows
  // on screen - otherwise collapsing a branch would quietly take its flips out of the
  // URL on the next change.
  const onChange = renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  await userEvent.click(twisty("Collapse", "Car"));

  await userEvent.click(checkbox("Groceries"));

  expect(onChange.mock.calls).toEqual([
    [{ root: true, selected: [], deselected: ["Car:Fuel", "Groceries"] }],
  ]);
});

test("drops a flip rather than keeping a box the ancestors already agree with", async () => {
  // Reticking Fuel does not add a selected Fuel beside the deselected one: it takes the
  // flip away, which is the default selection again and no category key at all.
  const onChange = renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Fuel"));
  expect(onChange.mock.calls).toEqual([[EVERYTHING]]);
});

test("stays open after a tick, so several can be picked in a row", async () => {
  renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(checkbox("Groceries"));
  expect(screen.getByRole("group", { name: "Categories" })).toBeTruthy();
});

test("keeps both actions in place, disabling the one the selection is already at", async () => {
  // Present rather than absent, so the panel is the same size whatever is selected -
  // and two buttons rather than one, now that all and nothing are different states.
  renderPicker();
  await userEvent.click(trigger());
  expect(button("Select all").disabled).toBe(true);
  expect(button("Select none").disabled).toBe(false);
});

test("disables the other action at the other extreme", async () => {
  renderPicker(NOTHING);
  await userEvent.click(trigger());
  expect(button("Select all").disabled).toBe(false);
  expect(button("Select none").disabled).toBe(true);
});

test("goes back to every category in one click", async () => {
  // Every flip dropped, not merely the root reselected: a deselected path left behind
  // would be a key the URL could not be rid of.
  const onChange = renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  await userEvent.click(button("Select all"));
  expect(onChange.mock.calls).toEqual([[EVERYTHING]]);
});

test("empties the selection in one click", async () => {
  // The state expenses are added to one at a time, which no sequence of unticks could
  // reach in fewer clicks than there are categories.
  const onChange = renderPicker(WITHOUT_FUEL);
  await userEvent.click(trigger());
  await userEvent.click(button("Select none"));
  expect(onChange.mock.calls).toEqual([[NOTHING]]);
});

test("closes when a click lands outside it", async () => {
  renderPicker();
  await userEvent.click(trigger());
  screen.getByRole("group", { name: "Categories" });

  await userEvent.click(document.body);

  expect(screen.queryByRole("group")).toBeNull();
});

test("closes on Escape and hands focus back to the trigger", async () => {
  renderPicker();
  await userEvent.click(trigger());
  screen.getByRole("group", { name: "Categories" });

  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("group")).toBeNull();
  expect(document.activeElement).toBe(trigger());
});

test("closes again on a second click of the trigger", async () => {
  renderPicker();
  await userEvent.click(trigger());
  await userEvent.click(trigger());
  expect(screen.queryByRole("group")).toBeNull();
});

test("can be worked from the keyboard", async () => {
  // Tab reaches the first row's controls from the trigger, its twisty before its box,
  // and Space works either: the disclosure pattern leaves focus on the trigger when it
  // opens, and APG asks Tab and Space of a twisty and nothing more.
  const onChange = renderPicker();
  await userEvent.click(trigger());
  await userEvent.tab();
  expect(document.activeElement).toBe(twisty("Expand", "Car"));
  await userEvent.keyboard(" ");
  expect(document.activeElement).toBe(twisty("Collapse", "Car"));

  await userEvent.tab();

  expect(document.activeElement).toBe(checkbox("Car"));
  await userEvent.keyboard(" ");
  expect(onChange.mock.calls).toEqual([
    [{ root: true, selected: [], deselected: ["Car"] }],
  ]);
});

test("is disabled when told to be", async () => {
  renderPicker(EVERYTHING, [], true);
  expect(trigger().hasAttribute("disabled")).toBe(true);
  await userEvent.click(trigger());
  expect(screen.queryByRole("group")).toBeNull();
});

test("shows a category nobody offered rather than silently dropping it", async () => {
  // Reachable by typing a name into the address bar: the URL is passed to the backend
  // unchecked, so the control has to agree with the request that is in flight.
  // A path, because that is what the address bar carries: it has no parent in the tree
  // to sit under, so it is labelled in full, listed flat ahead of the rest, and has
  // nothing to disclose.
  renderPicker({ root: false, selected: ["Travel:Spain"], deselected: [] }, [
    { category: "Car", name: "Car" },
    { category: "Groceries", name: "Groceries" },
  ]);
  expect(trigger().textContent).toBe("Travel:Spain");
  await userEvent.click(trigger());
  expect(indents()).toEqual([
    ["Travel:Spain", "pl-0"],
    ["Car", "pl-0"],
    ["Groceries", "pl-0"],
  ]);
  expect(twisties()).toEqual([]);
  expect(checkboxes()).toEqual([
    ["Travel:Spain", true],
    ["Car", false],
    ["Groceries", false],
  ]);
});
