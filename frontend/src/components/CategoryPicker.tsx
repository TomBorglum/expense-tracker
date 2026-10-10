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

// One row of the panel: the path a tick reports, the label it shows, and how deep it
// sits.
interface Row {
  readonly category: string;
  readonly label: string;
  readonly depth: number;
}

// Static, because Tailwind reads its classes out of this source: a pl-${depth} template
// would compile to nothing. The last one covers anything deeper than the picker asks for.
const INDENT = ["pl-0", "pl-4", "pl-8", "pl-12"] as const;

// The panel's rows, depth-first from the roots. Built from `parent` rather than from the
// order the list arrived in: path order is nearly pre-order, but a level name starting
// below ":" interleaves - Settlement2024 sorts between Settlement and Settlement:Alice -
// so a walk that assumed the list was contiguous would nest it under Settlement.
function rows(options: readonly Category[], selected: readonly string[]): Row[] {
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
  function walk(parent: string, depth: number) {
    for (const option of children.get(parent) ?? []) {
      tree.push({ category: option.category, label: option.name, depth });
      walk(option.category, depth + 1);
    }
  }
  walk("", 0);
  // A selected path nobody offered goes first and flat, labelled in full: it has no
  // parent here to sit under. The rule CurrencySelect applies to a code typed into the
  // address bar.
  const offered = new Set(tree.map((row) => row.category));
  return [
    ...selected
      .filter((path) => !offered.has(path))
      .map((path) => ({ category: path, label: path, depth: 0 })),
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
// beyond whether it is open and makes no request: the selection is the URL's, and the
// options are the tree the categories endpoint listed. An empty selection is every
// category, which is what an absent parameter means to the backend.
export function CategoryPicker({
  selected,
  options,
  disabled,
  onChange,
}: CategoryPickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const shown = rows(options, selected);

  useDismiss(open, containerRef, (restoreFocus) => {
    setOpen(false);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  });

  // Reported in row order whatever order the boxes were ticked in, so one selection is
  // one URL. Ticking a parent does nothing to its children: the backend already reads a
  // node as its whole subtree, and a parent beside one of its own children is a request
  // in its own right - on /totals it splits that child out of the parent's total.
  function toggle(category: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) {
      next.add(category);
    } else {
      next.delete(category);
    }
    onChange(shown.map((row) => row.category).filter((path) => next.has(path)));
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
              <label
                key={row.category}
                className={`flex cursor-pointer items-center gap-2 ${INDENT[Math.min(row.depth, INDENT.length - 1)]}`}
              >
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
