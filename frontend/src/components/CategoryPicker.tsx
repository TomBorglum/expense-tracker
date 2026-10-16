import { useRef, useState } from "react";

import { type Category } from "../api/categories";
import { FilterField } from "./FilterField";
import { useDismiss } from "./useDismiss";

interface CategoryPickerProps {
  readonly selected: readonly string[];
  readonly options: readonly Category[];
  readonly disabled: boolean;
  readonly onChange: (categories: string[]) => void;
}

// One row of the panel: the path a tick reports, the label it shows, how deep it sits,
// whether it has children to disclose, whether it is disclosing them, and whether every
// node above it is.
interface Row {
  readonly category: string;
  readonly label: string;
  readonly depth: number;
  readonly expandable: boolean;
  readonly expanded: boolean;
  readonly visible: boolean;
}

// Static, because Tailwind reads its classes out of this source: a pl-${depth} template
// would compile to nothing. The last one covers anything deeper than the picker asks for.
const INDENT = ["pl-0", "pl-4", "pl-8", "pl-12"] as const;

// The paths that have to be open for every selected category to be reachable: each
// selected node's parents, walked up through `parent` rather than by splitting a path -
// the separator is the backend's. The `has` guard skips work already done, and is what
// stops a payload whose parents form a cycle.
function ancestorsOf(
  options: readonly Category[],
  selected: readonly string[],
): Set<string> {
  const parents = new Map(options.map((option) => [option.category, option.parent]));
  const open = new Set<string>();
  for (const path of selected) {
    let parent = parents.get(path);
    while (parent !== undefined && !open.has(parent)) {
      open.add(parent);
      parent = parents.get(parent);
    }
  }
  return open;
}

// The panel's rows, depth-first from the roots - the whole tree whatever is expanded. A
// row under a collapsed node is marked rather than dropped, because the selection is
// reported in this order and a tick that is out of sight has to survive that. Built from
// `parent` rather than from the order the list arrived in: path order is nearly
// pre-order, but a level name starting below ":" interleaves - Settlement2024 sorts
// between Settlement and Settlement:Alice - so a walk that assumed the list was
// contiguous would nest it under Settlement.
function rows(
  options: readonly Category[],
  selected: readonly string[],
  isExpanded: (category: string) => boolean,
): Row[] {
  const children = new Map<string, Category[]>();
  for (const option of options) {
    // "" is the root key, which no path can collide with: a level is never empty.
    const key = option.parent ?? "";
    const siblings = children.get(key);
    if (siblings === undefined) {
      children.set(key, [option]);
    } else {
      siblings.push(option);
    }
  }
  const tree: Row[] = [];
  function walk(parent: string, depth: number, open: boolean) {
    for (const option of children.get(parent) ?? []) {
      const expanded = isExpanded(option.category);
      tree.push({
        category: option.category,
        label: option.name,
        depth,
        expandable: children.has(option.category),
        expanded,
        visible: open,
      });
      walk(option.category, depth + 1, open && expanded);
    }
  }
  walk("", 0, true);
  // A selected path nobody offered goes first and flat, labelled in full: it has no
  // parent here to sit under, and so nothing to disclose either. The rule CurrencySelect
  // applies to a code typed into the address bar.
  const offered = new Set(tree.map((row) => row.category));
  return [
    ...selected
      .filter((path) => !offered.has(path))
      .map((path) => ({
        category: path,
        label: path,
        depth: 0,
        expandable: false,
        expanded: false,
        visible: true,
      })),
    ...tree,
  ];
}

// What the trigger reads: the one path while it fits beside the other controls, a count
// once it would not. A pair of paths is longer than w-44 shows, so two is already a
// count where two flat names were not.
function summarize(selected: readonly string[]): string {
  if (selected.length === 0) {
    return "All categories";
  }
  return selected.length === 1 ? selected[0] : `${String(selected.length)} categories`;
}

// The control that narrows the expenses to one or more categories. It holds no state
// beyond whether it is open and which nodes a twisty was clicked on, and makes no
// request: the selection is the URL's, and the options are the tree the categories
// endpoint listed. An empty selection is every category, which is what an absent
// parameter means to the backend.
export function CategoryPicker({
  selected,
  options,
  disabled,
  onChange,
}: CategoryPickerProps) {
  const [open, setOpen] = useState(false);
  // Only the nodes a twisty was actually clicked on. What a row discloses is worked out
  // below rather than stored: the options arrive from a request, so a set seeded when
  // the panel first rendered would be seeded before there was a tree to seed it from.
  const [toggled, setToggled] = useState<ReadonlyMap<string, boolean>>(() => new Map());
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // Expanded because a twisty said so, or because a selection sits below it - which is
  // what keeps a ticked child reachable in a panel that opens at the roots. A map of
  // clicks rather than a set of open paths: a set would make those ancestors
  // permanently open and their own twisties inert.
  const byDefault = ancestorsOf(options, selected);
  function isExpanded(category: string) {
    return toggled.get(category) ?? byDefault.has(category);
  }
  const all = rows(options, selected, isExpanded);
  const shown = all.filter((row) => row.visible);

  useDismiss(open, containerRef, (restoreFocus) => {
    setOpen(false);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  });

  // Reported in row order whatever order the boxes were ticked in, so one selection is
  // one URL - and against the whole tree rather than the rows on screen, so collapsing
  // a branch cannot drop a tick inside it. Ticking a parent does nothing to its
  // children: the backend already reads a node as its whole subtree, and a parent beside
  // one of its own children is a request in its own right - on /totals it splits that
  // child out of the parent's total.
  function toggle(category: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) {
      next.add(category);
    } else {
      next.delete(category);
    }
    onChange(all.map((row) => row.category).filter((path) => next.has(path)));
  }

  function toggleExpanded(category: string) {
    const next = new Map(toggled);
    next.set(category, !isExpanded(category));
    setToggled(next);
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
          <span className="min-w-0 truncate">{summarize(selected)}</span>
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
                key={row.category}
                className={`flex items-center gap-2 ${INDENT[Math.min(row.depth, INDENT.length - 1)]}`}
              >
                {row.expandable ? (
                  // Not daisyUI's collapse: its three forms are a tabindex that closes
                  // on blur, a checkbox this fieldset is full of already, and a
                  // <summary> @testing-library/dom gives no role. No btn class either -
                  // this is a sign in the list, and the footer stays the one button.
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
                      toggleExpanded(row.category);
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
                    checked={selected.includes(row.category)}
                    onChange={(event) => {
                      toggle(row.category, event.target.checked);
                    }}
                  />
                  {row.label}
                </label>
              </div>
            ))}
            {/* Always in the panel, disabled rather than absent while there is nothing to
                clear: it is wider than the list, so a panel it came and went from would
                change size, and a right-anchored one shifts as it does. */}
            <button
              type="button"
              className="btn btn-ghost btn-sm text-sm font-normal"
              disabled={selected.length === 0}
              onClick={() => {
                onChange([]);
              }}
            >
              Clear selection
            </button>
          </fieldset>
        )}
      </div>
    </FilterField>
  );
}
