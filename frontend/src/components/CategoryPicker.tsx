import { useRef, useState } from "react";

import { type Category } from "../api/categories";
import {
  categoryParents,
  type CategoryParents,
  type CategorySelection,
  EVERYTHING,
  isEverything,
  isNothing,
  isSelected,
  NOTHING,
  toggled,
} from "../categorySelection";
import { FilterField } from "./FilterField";
import { useDismiss } from "./useDismiss";

interface CategoryPickerProps {
  readonly selection: CategorySelection;
  readonly options: readonly Category[];
  readonly disabled: boolean;
  readonly onChange: (selection: CategorySelection) => void;
}

// One row of the panel: the slug a tick reports, the label it shows, how deep it sits,
// whether it has children to disclose, whether it is disclosing them, whether every node
// above it is, its own sign, and whether its subtree carries the other one.
interface Row {
  readonly slug: string;
  readonly label: string;
  readonly depth: number;
  readonly expandable: boolean;
  readonly expanded: boolean;
  readonly visible: boolean;
  readonly checked: boolean;
  readonly mixed: boolean;
}

// Static, because Tailwind reads its classes out of this source: a pl-${depth} template
// would compile to nothing. The last one covers anything deeper than the picker asks for.
const INDENT = ["pl-0", "pl-4", "pl-8", "pl-12"] as const;

// Both lists together, which is what the panel has to show and keep reachable: either
// kind of flip is a point the selection changes at.
function flipsOf(selection: CategorySelection): string[] {
  return [...selection.selected, ...selection.deselected];
}

// The slugs that have to be open for every flip to be reachable: each flipped node's
// parents, walked up through `parent_slug` rather than by splitting a slug - the
// separator is the backend's. The `has` guard skips work already done, and is what stops
// a payload whose parents form a cycle.
function ancestorsOf(parents: CategoryParents, flips: readonly string[]): Set<string> {
  const open = new Set<string>();
  for (const slug of flips) {
    let parent = parents.get(slug);
    while (parent !== undefined && !open.has(parent)) {
      open.add(parent);
      parent = parents.get(parent);
    }
  }
  return open;
}

// The panel's rows, depth-first from the roots - the whole tree whatever is expanded. A
// row under a collapsed node is marked rather than dropped, because the selection is
// reported in this order and a flip that is out of sight has to survive that. Built from
// `parent_slug` rather than from the order the list arrived in: the list arrives in path
// order, which is nearly pre-order, but a level name starting below ":" interleaves -
// Settlement2024 sorts between Settlement and Settlement:Alice - so a walk that assumed
// the list was contiguous would nest it under Settlement.
function rows(
  options: readonly Category[],
  selection: CategorySelection,
  parents: CategoryParents,
  isExpanded: (slug: string) => boolean,
): Row[] {
  const children = new Map<string, Category[]>();
  for (const option of options) {
    // "" is the root key, which no slug can collide with: a level is never empty.
    const key = option.parent_slug ?? "";
    const siblings = children.get(key);
    if (siblings === undefined) {
      children.set(key, [option]);
    } else {
      siblings.push(option);
    }
  }
  // Which nodes carry a sign their own subtree disagrees with, worked out bottom-up:
  // a node's sign says nothing about a flip below it, and that disagreement is the
  // third state a box has to show.
  const mixed = new Set<string>();
  function signs(slug: string): Set<boolean> {
    const seen = new Set([isSelected(selection, slug, parents)]);
    for (const child of children.get(slug) ?? []) {
      for (const sign of signs(child.slug)) {
        seen.add(sign);
      }
    }
    if (seen.size > 1) {
      mixed.add(slug);
    }
    return seen;
  }
  for (const root of children.get("") ?? []) {
    signs(root.slug);
  }
  const tree: Row[] = [];
  function walk(parent: string, depth: number, open: boolean) {
    for (const option of children.get(parent) ?? []) {
      const expanded = isExpanded(option.slug);
      tree.push({
        slug: option.slug,
        label: option.name,
        depth,
        expandable: children.has(option.slug),
        expanded,
        visible: open,
        checked: isSelected(selection, option.slug, parents),
        mixed: mixed.has(option.slug),
      });
      walk(option.slug, depth + 1, open && expanded);
    }
  }
  walk("", 0, true);
  // A flipped slug nobody offered goes first and flat, labelled with the slug itself:
  // it has no parent here to sit under, and so nothing to disclose either, nothing below
  // it to disagree with, and no name beside it to label it by. The rule CurrencySelect
  // applies to a code typed into the address bar.
  const offered = new Set(tree.map((row) => row.slug));
  return [
    ...flipsOf(selection)
      .filter((slug) => !offered.has(slug))
      .map((slug) => ({
        slug,
        label: slug,
        depth: 0,
        expandable: false,
        expanded: false,
        visible: true,
        checked: isSelected(selection, slug, parents),
        mixed: false,
      })),
    ...tree,
  ];
}

// What the trigger reads: the two extremes by name, and otherwise the side the selection
// is stated from - what is missing from everything, or what was picked out of nothing.
// A single slug while it fits beside the other controls, a count once it would not; a
// pair of slugs is longer than w-44 shows, so two is already a count.
function summarize(selection: CategorySelection): string {
  if (isEverything(selection)) {
    return "All categories";
  }
  if (isNothing(selection)) {
    return "No categories";
  }
  if (selection.root) {
    const dropped = selection.deselected;
    return dropped.length === 1
      ? `All but ${dropped[0]}`
      : `All but ${String(dropped.length)}`;
  }
  const picked = selection.selected;
  return picked.length === 1 ? picked[0] : `${String(picked.length)} categories`;
}

// The control that narrows the expenses to a selection of categories. It holds no state
// beyond whether it is open and which nodes a twisty was clicked on, and makes no
// request: the selection is the URL's, and the options are the tree the categories
// endpoint listed. Every box is ticked by default, which is the selection every category
// is, and a tick carries its whole subtree with it.
export function CategoryPicker({
  selection,
  options,
  disabled,
  onChange,
}: CategoryPickerProps) {
  const [open, setOpen] = useState(false);
  // Only the nodes a twisty was actually clicked on. What a row discloses is worked out
  // below rather than stored: the options arrive from a request, so a set seeded when
  // the panel first rendered would be seeded before there was a tree to seed it from.
  const [clicked, setClicked] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const parents = categoryParents(options);
  // Expanded because a twisty said so, or because a flip sits below it - which is what
  // keeps a changed child reachable in a panel that opens at the roots. A map of clicks
  // rather than a set of open paths: a set would make those ancestors permanently open
  // and their own twisties inert.
  const byDefault = ancestorsOf(parents, flipsOf(selection));
  function isExpanded(slug: string) {
    return clicked.get(slug) ?? byDefault.has(slug);
  }
  const all = rows(options, selection, parents, isExpanded);
  const shown = all.filter((row) => row.visible);

  useDismiss(open, containerRef, (restoreFocus) => {
    setOpen(false);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  });

  // Reported in row order whatever order the boxes were ticked in, so one selection is
  // one URL - and against the whole tree rather than the rows on screen, so collapsing
  // a branch cannot drop a flip inside it. Unticking a parent carries its children with
  // it: the backend reads a node as its whole subtree, and every flip below the one
  // being set goes, so the cascade cannot leave part of the subtree behind.
  function toggle(slug: string, checked: boolean) {
    onChange(
      toggled(
        selection,
        slug,
        checked,
        parents,
        all.map((row) => row.slug),
      ),
    );
  }

  function toggleExpanded(slug: string) {
    const next = new Map(clicked);
    next.set(slug, !isExpanded(slug));
    setClicked(next);
  }

  return (
    <FilterField label="Categories" labelId="categories-label">
      {/* Positioned by hand for the reason DateRangePicker gives: the open state is
          React's, and daisyUI's dropdown classes would hide the panel the moment focus
          left it. This div is what an outside click is measured against. */}
      <div ref={containerRef} className="relative">
        <button
          id="categories-value"
          ref={triggerRef}
          type="button"
          aria-expanded={open}
          aria-controls="categories-panel"
          aria-labelledby="categories-label categories-value"
          // A fixed width rather than the text's own: the label changes with every tick,
          // and a trigger that grew with it would slide the whole filter row along. A
          // long path is cut with an ellipsis; the panel lists it in full.
          className="input w-44 cursor-pointer"
          disabled={disabled}
          onClick={() => {
            setOpen((current) => !current);
          }}
        >
          <span className="min-w-0 truncate">{summarize(selection)}</span>
        </button>
        {open && (
          // text-sm because daisyUI's fieldset writes 0.75rem; the labels carry none of
          // its label class, which dims a caption to 60% and these are the choices.
          <fieldset
            id="categories-panel"
            className="absolute top-full right-0 z-10 mt-2 flex w-max flex-col gap-1 rounded-box bg-base-100 p-2 text-sm shadow-lg"
          >
            <legend className="sr-only">Categories</legend>
            {shown.map((row) => (
              // The twisty sits outside the label: inside it, a click on the sign would
              // tick the box. So the indent moves out here with it.
              <div
                key={row.slug}
                className={`flex items-center gap-2 ${INDENT[Math.min(row.depth, INDENT.length - 1)]}`}
              >
                {row.expandable ? (
                  // Not daisyUI's collapse: its three forms are a tabindex that closes
                  // on blur, a checkbox this fieldset is full of already, and a
                  // <summary> @testing-library/dom gives no role. No btn class either -
                  // this is a sign in the list, and the footer stays the buttons.
                  <button
                    type="button"
                    // The name carries the verb and the sign is hidden: "+" names
                    // nothing, and a name saying which way it goes is what the panel is
                    // queried by. No aria-controls - the rows are a flat list with a
                    // depth, so there is no element holding a node's children to name.
                    aria-label={`${row.expanded ? "Collapse" : "Expand"} ${row.label}`}
                    aria-expanded={row.expanded}
                    className="w-4 cursor-pointer text-center leading-none"
                    onClick={() => {
                      toggleExpanded(row.slug);
                    }}
                  >
                    <span aria-hidden="true">{row.expanded ? "-" : "+"}</span>
                  </button>
                ) : (
                  // The twisty's width kept rather than closed up, so every tick in a
                  // generation lines up whether its row has children or not: the indent
                  // is what reads as depth.
                  <span className="w-4" />
                )}
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={row.checked}
                    // indeterminate is a DOM property with no attribute behind it, so
                    // JSX cannot carry it: the ref is what puts the dash on a node whose
                    // own subtree disagrees with it.
                    ref={(box) => {
                      if (box !== null) {
                        box.indeterminate = row.mixed;
                      }
                    }}
                    onChange={(event) => {
                      toggle(row.slug, event.target.checked);
                    }}
                  />
                  {row.label}
                </label>
              </div>
            ))}
            {/* Two actions rather than the one this panel had: now that all and nothing
                are different states, a single button could not say which it went to.
                Each is disabled in the state it would produce, and both stay in place so
                a right-anchored panel does not change size as the selection changes. */}
            <div className="flex gap-1">
              <button
                type="button"
                className="btn btn-ghost btn-sm grow text-sm font-normal"
                disabled={isEverything(selection)}
                onClick={() => {
                  onChange(EVERYTHING);
                }}
              >
                Select all
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm grow text-sm font-normal"
                disabled={isNothing(selection)}
                onClick={() => {
                  onChange(NOTHING);
                }}
              >
                Select none
              </button>
            </div>
          </fieldset>
        )}
      </div>
    </FilterField>
  );
}
