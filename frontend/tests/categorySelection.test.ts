import { expect, test } from "vitest";

import { type Category } from "@/api/categories";
import {
  categoryParents,
  type CategorySelection,
  EVERYTHING,
  isEverything,
  isNothing,
  isSelected,
  NOTHING,
  selectionFromSearch,
  selectionToSearch,
  toggled,
} from "@/categorySelection";

// One branch three levels deep, a sibling of its root that merely starts with the same
// characters, and a second root - so a flip is told from a prefix of characters, and a
// cascade has a grandchild to reach.
const OPTIONS: Category[] = [
  { category: "Car", name: "Car" },
  { category: "Car2024", name: "Car2024" },
  { category: "Car:Fuel", name: "Fuel", parent: "Car" },
  { category: "Car:Fuel:Diesel", name: "Diesel", parent: "Car:Fuel" },
  { category: "Groceries", name: "Groceries" },
];
const PARENTS = categoryParents(OPTIONS);
// The order the panel walks its rows in, which is the order a flip is reported in.
const ORDER = ["Car", "Car:Fuel", "Car:Fuel:Diesel", "Car2024", "Groceries"];
const PATHS = ORDER;

function signs(selection: CategorySelection): Record<string, boolean> {
  return Object.fromEntries(
    PATHS.map((path) => [path, isSelected(selection, path, PARENTS)]),
  );
}

test("the default selects every category", () => {
  expect(signs(EVERYTHING)).toEqual({
    Car: true,
    "Car:Fuel": true,
    "Car:Fuel:Diesel": true,
    Car2024: true,
    Groceries: true,
  });
  expect(isEverything(EVERYTHING)).toBe(true);
  expect(isNothing(EVERYTHING)).toBe(false);
});

test("the empty selection selects none of them", () => {
  expect(Object.values(signs(NOTHING))).toEqual([false, false, false, false, false]);
  expect(isNothing(NOTHING)).toBe(true);
});

test("a deselected path takes its whole subtree with it, by level", () => {
  // Car2024 is the control: it shares every character of the prefix and is not under
  // Car, because the walk goes through `parent` and never splits a path.
  expect(signs({ root: true, selected: [], deselected: ["Car"] })).toEqual({
    Car: false,
    "Car:Fuel": false,
    "Car:Fuel:Diesel": false,
    Car2024: true,
    Groceries: true,
  });
});

test("the longest flip over a path decides", () => {
  // The rule itself, and the mirror of the backend's CASE: read upwards, the first flip
  // met is the longest one above the path, so a child keeps a sign its parent lost.
  expect(signs({ root: true, selected: ["Car:Fuel"], deselected: ["Car"] })).toEqual({
    Car: false,
    "Car:Fuel": true,
    "Car:Fuel:Diesel": true,
    Car2024: true,
    Groceries: true,
  });
});

test("a path the tree does not offer answers from its own flip alone", () => {
  // Typed into the address bar: it has no parent here to climb to, so the selection
  // shows it the sign the URL gave it rather than the root's.
  const selection = { root: false, selected: ["Travel:Spain"], deselected: [] };
  expect(isSelected(selection, "Travel:Spain", PARENTS)).toBe(true);
  expect(isSelected(selection, "Groceries", PARENTS)).toBe(false);
});

test("unticking from the default is one flip, not one per category left", () => {
  expect(toggled(EVERYTHING, "Car", false, PARENTS, ORDER)).toEqual({
    root: true,
    selected: [],
    deselected: ["Car"],
  });
});

test("ticking a box again leaves the selection exactly as it was", () => {
  // No flip where the ancestors already agree, which is what keeps the URL to the points
  // the selection changes at.
  const dropped = toggled(EVERYTHING, "Car", false, PARENTS, ORDER);
  expect(toggled(dropped, "Car", true, PARENTS, ORDER)).toEqual(EVERYTHING);
});

test("unticking inside an already unticked subtree adds nothing", () => {
  const dropped = { root: true, selected: [], deselected: ["Car"] };
  expect(toggled(dropped, "Car:Fuel", false, PARENTS, ORDER)).toEqual(dropped);
});

test("unticking a parent carries every flip below it away", () => {
  // The cascade: a descendant flip of the other sign would outlive it and keep part of
  // the subtree ticked, which is what "unticking a parent unticks its children" means.
  const kept = { root: true, selected: ["Car:Fuel:Diesel"], deselected: ["Car:Fuel"] };
  expect(toggled(kept, "Car", false, PARENTS, ORDER)).toEqual({
    root: true,
    selected: [],
    deselected: ["Car"],
  });
});

test("reports a list in row order, whatever order the boxes were ticked in", () => {
  // One selection is one URL: unticking Groceries then Car spells the same as the other
  // way round.
  const first = toggled(EVERYTHING, "Groceries", false, PARENTS, ORDER);
  expect(toggled(first, "Car", false, PARENTS, ORDER).deselected).toEqual([
    "Car",
    "Groceries",
  ]);
});

test("keeps a flip the rows do not hold rather than dropping it", () => {
  // A path nobody offered is reported first and kept: the panel reports what the URL
  // holds, not only what it could show.
  const unoffered = { root: false, selected: ["Travel:Spain"], deselected: [] };
  expect(toggled(unoffered, "Groceries", true, PARENTS, ORDER).selected).toEqual([
    "Travel:Spain",
    "Groceries",
  ]);
});

test("the default sends no category key at all", () => {
  expect(selectionToSearch(EVERYTHING)).toEqual({
    category: undefined,
    not_category: undefined,
    category_default: undefined,
  });
});

test("the empty selection is the flag alone", () => {
  expect(selectionToSearch(NOTHING)).toEqual({
    category: undefined,
    not_category: undefined,
    category_default: "none",
  });
});

test("a deselection needs no flag, the root being selected already", () => {
  expect(selectionToSearch({ root: true, selected: [], deselected: ["Car"] })).toEqual({
    category: undefined,
    not_category: ["Car"],
    category_default: undefined,
  });
});

test("a selected path needs no flag either, being what implies the root", () => {
  // The same URL the view sent before any of this: ?category=Car means Car and no
  // others on both sides.
  expect(selectionToSearch({ root: false, selected: ["Car"], deselected: [] })).toEqual(
    {
      category: ["Car"],
      not_category: undefined,
      category_default: undefined,
    },
  );
});

test("a root kept selected beside a selected path sends the flag", () => {
  // The one state the implied reading gets wrong, which is why `all` is sendable.
  expect(
    selectionToSearch({
      root: true,
      selected: ["Car:Fuel"],
      deselected: ["Car"],
    }),
  ).toEqual({
    category: ["Car:Fuel"],
    not_category: ["Car"],
    category_default: "all",
  });
});

test("reads a selection back off the search it was written to", () => {
  const selections: CategorySelection[] = [
    EVERYTHING,
    NOTHING,
    { root: true, selected: [], deselected: ["Car"] },
    { root: false, selected: ["Car"], deselected: [] },
    { root: true, selected: ["Car:Fuel"], deselected: ["Car"] },
    { root: false, selected: ["Car"], deselected: ["Car:Fuel"] },
  ];
  for (const selection of selections) {
    expect(selectionFromSearch(selectionToSearch(selection))).toEqual(selection);
  }
});

test("an absent flag reads the root off the selected list, as the backend does", () => {
  expect(selectionFromSearch({ category: ["Car"] }).root).toBe(false);
  expect(selectionFromSearch({ not_category: ["Car"] }).root).toBe(true);
  expect(selectionFromSearch({}).root).toBe(true);
});

test("a flip inside a root of the same sign is not a third state", () => {
  // What everything() and nothing() mean on the backend: such a flip narrows nothing,
  // so it does not stop a selection being every category or none.
  expect(isEverything({ root: true, selected: ["Car"], deselected: [] })).toBe(true);
  expect(isNothing({ root: false, selected: [], deselected: ["Car"] })).toBe(true);
});
