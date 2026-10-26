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
// cascade has a grandchild to reach. Every path carries its slug, which is the value
// this model deals in: the path is here only to show the two are different.
const OPTIONS: Category[] = [
  { category: "Car", name: "Car", slug: "car" },
  { category: "Car2024", name: "Car2024", slug: "car2024" },
  {
    category: "Car:Fuel",
    name: "Fuel",
    slug: "car:fuel",
    parent: "Car",
    parent_slug: "car",
  },
  {
    category: "Car:Fuel:Diesel",
    name: "Diesel",
    slug: "car:fuel:diesel",
    parent: "Car:Fuel",
    parent_slug: "car:fuel",
  },
  { category: "Groceries", name: "Groceries", slug: "groceries" },
];
const PARENTS = categoryParents(OPTIONS);
// The order the panel walks its rows in, which is the order a flip is reported in.
const ORDER = ["car", "car:fuel", "car:fuel:diesel", "car2024", "groceries"];
const SLUGS = ORDER;

function signs(selection: CategorySelection): Record<string, boolean> {
  return Object.fromEntries(
    SLUGS.map((slug) => [slug, isSelected(selection, slug, PARENTS)]),
  );
}

test("the default selects every category", () => {
  expect(signs(EVERYTHING)).toEqual({
    car: true,
    "car:fuel": true,
    "car:fuel:diesel": true,
    car2024: true,
    groceries: true,
  });
  expect(isEverything(EVERYTHING)).toBe(true);
  expect(isNothing(EVERYTHING)).toBe(false);
});

test("the empty selection selects none of them", () => {
  expect(Object.values(signs(NOTHING))).toEqual([false, false, false, false, false]);
  expect(isNothing(NOTHING)).toBe(true);
});

test("a deselected slug takes its whole subtree with it, by level", () => {
  // car2024 is the control: it shares every character of the prefix and is not under
  // car, because the walk goes through `parent_slug` and never splits a slug.
  expect(signs({ root: true, selected: [], deselected: ["car"] })).toEqual({
    car: false,
    "car:fuel": false,
    "car:fuel:diesel": false,
    car2024: true,
    groceries: true,
  });
});

test("the longest flip over a slug decides", () => {
  // The rule itself, and the mirror of the backend's CASE: read upwards, the first flip
  // met is the longest one above the slug, so a child keeps a sign its parent lost.
  expect(signs({ root: true, selected: ["car:fuel"], deselected: ["car"] })).toEqual({
    car: false,
    "car:fuel": true,
    "car:fuel:diesel": true,
    car2024: true,
    groceries: true,
  });
});

test("a slug the tree does not offer answers from its own flip alone", () => {
  // Typed into the address bar: it has no parent here to climb to, so the selection
  // shows it the sign the URL gave it rather than the root's.
  const selection = { root: false, selected: ["travel:spain"], deselected: [] };
  expect(isSelected(selection, "travel:spain", PARENTS)).toBe(true);
  expect(isSelected(selection, "groceries", PARENTS)).toBe(false);
});

test("unticking from the default is one flip, not one per category left", () => {
  expect(toggled(EVERYTHING, "car", false, PARENTS, ORDER)).toEqual({
    root: true,
    selected: [],
    deselected: ["car"],
  });
});

test("ticking a box again leaves the selection exactly as it was", () => {
  // No flip where the ancestors already agree, which is what keeps the URL to the points
  // the selection changes at.
  const dropped = toggled(EVERYTHING, "car", false, PARENTS, ORDER);
  expect(toggled(dropped, "car", true, PARENTS, ORDER)).toEqual(EVERYTHING);
});

test("unticking inside an already unticked subtree adds nothing", () => {
  const dropped = { root: true, selected: [], deselected: ["car"] };
  expect(toggled(dropped, "car:fuel", false, PARENTS, ORDER)).toEqual(dropped);
});

test("unticking a parent carries every flip below it away", () => {
  // The cascade: a descendant flip of the other sign would outlive it and keep part of
  // the subtree ticked, which is what "unticking a parent unticks its children" means.
  const kept = { root: true, selected: ["car:fuel:diesel"], deselected: ["car:fuel"] };
  expect(toggled(kept, "car", false, PARENTS, ORDER)).toEqual({
    root: true,
    selected: [],
    deselected: ["car"],
  });
});

test("reports a list in row order, whatever order the boxes were ticked in", () => {
  // One selection is one URL: unticking groceries then car spells the same as the other
  // way round.
  const first = toggled(EVERYTHING, "groceries", false, PARENTS, ORDER);
  expect(toggled(first, "car", false, PARENTS, ORDER).deselected).toEqual([
    "car",
    "groceries",
  ]);
});

test("keeps a flip the rows do not hold rather than dropping it", () => {
  // A slug nobody offered is reported first and kept: the panel reports what the URL
  // holds, not only what it could show.
  const unoffered = { root: false, selected: ["travel:spain"], deselected: [] };
  expect(toggled(unoffered, "groceries", true, PARENTS, ORDER).selected).toEqual([
    "travel:spain",
    "groceries",
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
  expect(selectionToSearch({ root: true, selected: [], deselected: ["car"] })).toEqual({
    category: undefined,
    not_category: ["car"],
    category_default: undefined,
  });
});

test("a selected slug needs no flag either, being what implies the root", () => {
  // The same URL the view sent before any of this: ?category=car means car and no
  // others on both sides.
  expect(selectionToSearch({ root: false, selected: ["car"], deselected: [] })).toEqual(
    {
      category: ["car"],
      not_category: undefined,
      category_default: undefined,
    },
  );
});

test("a root kept selected beside a selected slug sends the flag", () => {
  // The one state the implied reading gets wrong, which is why `all` is sendable.
  expect(
    selectionToSearch({
      root: true,
      selected: ["car:fuel"],
      deselected: ["car"],
    }),
  ).toEqual({
    category: ["car:fuel"],
    not_category: ["car"],
    category_default: "all",
  });
});

test("reads a selection back off the search it was written to", () => {
  const selections: CategorySelection[] = [
    EVERYTHING,
    NOTHING,
    { root: true, selected: [], deselected: ["car"] },
    { root: false, selected: ["car"], deselected: [] },
    { root: true, selected: ["car:fuel"], deselected: ["car"] },
    { root: false, selected: ["car"], deselected: ["car:fuel"] },
  ];
  for (const selection of selections) {
    expect(selectionFromSearch(selectionToSearch(selection))).toEqual(selection);
  }
});

test("an absent flag reads the root off the selected list, as the backend does", () => {
  // All three keys spelled out, the way validateSearch hands them over: the search
  // leaves none of them out, it carries them undefined.
  const absent = {
    category: undefined,
    not_category: undefined,
    category_default: undefined,
  };
  expect(selectionFromSearch({ ...absent, category: ["car"] }).root).toBe(false);
  expect(selectionFromSearch({ ...absent, not_category: ["car"] }).root).toBe(true);
  expect(selectionFromSearch(absent).root).toBe(true);
});

test("a flip inside a root of the same sign is not a third state", () => {
  // What everything() and nothing() mean on the backend: such a flip narrows nothing,
  // so it does not stop a selection being every category or none.
  expect(isEverything({ root: true, selected: ["car"], deselected: [] })).toBe(true);
  expect(isNothing({ root: false, selected: [], deselected: ["car"] })).toBe(true);
});
