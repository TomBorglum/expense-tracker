import { ALL_CATEGORIES, type Category, NO_CATEGORIES } from "./api/categories";
import { type ExpensesQuery } from "./api/expenses";

// What a request selects: the root's own sign, and the paths that flip it. The mirror of
// CategorySelection in backend/src/expense_tracker/category_filter.py, down to the rule
// that resolves the two - a row is selected by the longest flip above it, and by the root
// when none of them is. Change them together.
export interface CategorySelection {
  readonly root: boolean;
  readonly selected: readonly string[];
  readonly deselected: readonly string[];
}

// The default, and the state Select all returns to: every category, flipping nothing.
export const EVERYTHING: CategorySelection = {
  root: true,
  selected: [],
  deselected: [],
};

// Its opposite, which is what the URL could not say before: nothing selected, so a
// selection can be built up instead of pared down.
export const NOTHING: CategorySelection = {
  root: false,
  selected: [],
  deselected: [],
};

// The parent of each offered path, which is what an ancestor walk needs. Nothing here
// splits a path: the separator is the backend's, and `parent` is the field that exists
// so this side never has to know it.
export type CategoryParents = ReadonlyMap<string, string | undefined>;

export function categoryParents(options: readonly Category[]): CategoryParents {
  return new Map(options.map((option) => [option.category, option.parent]));
}

// The three keys the selection is carried in, which is all selectionToSearch sets and
// all selectionFromSearch reads.
type CategorySearch = Pick<
  ExpensesQuery,
  "category" | "not_category" | "category_default"
>;

// Walked upwards, so the first flip met is the longest one above the path - the same
// first-match-wins the backend's CASE applies, read from the other end. A path the tree
// does not hold has no parent to climb to, so only its own flip counts, which is what
// keeps a URL value nobody offered showing the sign it was given.
export function isSelected(
  selection: CategorySelection,
  path: string,
  parents: CategoryParents,
): boolean {
  let node: string | undefined = path;
  while (node !== undefined) {
    if (selection.selected.includes(node)) {
      return true;
    }
    if (selection.deselected.includes(node)) {
      return false;
    }
    node = parents.get(node);
  }
  return selection.root;
}

function isUnder(path: string, ancestor: string, parents: CategoryParents): boolean {
  let node = parents.get(path);
  while (node !== undefined) {
    if (node === ancestor) {
      return true;
    }
    node = parents.get(node);
  }
  return false;
}

// One list in row order, whatever order the boxes were ticked in, so one selection is
// one URL. A flip the rows do not hold keeps its place rather than being dropped: the
// panel reports what the URL has, not only what it could show.
function inOrder(
  flips: readonly string[],
  order: readonly string[],
): readonly string[] {
  const held = new Set(flips);
  return [
    ...flips.filter((path) => !order.includes(path)),
    ...order.filter((path) => held.has(path)),
  ];
}

// The selection after one box was ticked or unticked, in the row order given.
export function toggled(
  selection: CategorySelection,
  path: string,
  checked: boolean,
  parents: CategoryParents,
  order: readonly string[],
): CategorySelection {
  // Every flip at or below the path goes: its own is being decided again, and a
  // descendant's would outlive the cascade and keep part of the subtree behind.
  const without = (flips: readonly string[]) =>
    flips.filter((flip) => flip !== path && !isUnder(flip, path, parents));
  const stripped: CategorySelection = {
    root: selection.root,
    selected: without(selection.selected),
    deselected: without(selection.deselected),
  };
  // No flip where the ancestors already agree, which is what keeps the URL to the points
  // the selection changes at - and what makes unticking a box and ticking it again leave
  // the address bar exactly as it was.
  if (isSelected(stripped, path, parents) === checked) {
    return stripped;
  }
  return checked
    ? { ...stripped, selected: inOrder([...stripped.selected, path], order) }
    : { ...stripped, deselected: inOrder([...stripped.deselected, path], order) };
}

// Everything and nothing on the backend's own terms: a flip inside a root of the same
// sign narrows nothing, so it is not what tells these two states from a third.
export function isEverything(selection: CategorySelection): boolean {
  return selection.root && selection.deselected.length === 0;
}

export function isNothing(selection: CategorySelection): boolean {
  return !selection.root && selection.selected.length === 0;
}

// What an absent ?category_default= works out to, and the only reason the frontend can
// leave it off: the backend reads the root as selected unless ?category= names a path.
function impliedRoot(selected: readonly string[]): boolean {
  return selected.length === 0;
}

export function selectionFromSearch(search: CategorySearch): CategorySelection {
  const selected = search.category ?? [];
  return {
    root:
      search.category_default === undefined
        ? impliedRoot(selected)
        : search.category_default === ALL_CATEGORIES,
    selected,
    deselected: search.not_category ?? [],
  };
}

export function selectionToSearch(selection: CategorySelection): CategorySearch {
  return {
    // Undefined rather than [], so a list that empties leaves the URL and the request
    // the way an absent key does.
    category: selection.selected.length === 0 ? undefined : [...selection.selected],
    not_category:
      selection.deselected.length === 0 ? undefined : [...selection.deselected],
    // Sent only where the implied reading is the wrong one - which is both of the two
    // states it exists for: nothing selected, and a root kept selected beside a path.
    category_default:
      impliedRoot(selection.selected) === selection.root
        ? undefined
        : selection.root
          ? ALL_CATEGORIES
          : NO_CATEGORIES,
  };
}
