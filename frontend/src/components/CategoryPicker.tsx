import { useRef, useState } from "react";

import { FilterField } from "./FilterField";
import { useDismiss } from "./useDismiss";

interface CategoryPickerProps {
  readonly selected: readonly string[];
  readonly options: readonly string[];
  readonly disabled: boolean;
  readonly onChange: (categories: string[]) => void;
}

// What the trigger reads: the names while two fit beside the other controls, a count
// once they would not.
function summarize(selected: readonly string[]): string {
  if (selected.length === 0) {
    return "All categories";
  }
  return selected.length <= 2
    ? selected.join(", ")
    : `${String(selected.length)} categories`;
}

// The control that narrows the expenses to one or more categories. It holds no state
// beyond whether it is open and makes no request: the selection is the URL's, and the
// options are the names the categories endpoint listed. An empty selection is every
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
  // A selected name nobody offered is still shown, ticked, ahead of the rest - the rule
  // CurrencySelect applies to a code typed into the address bar.
  const shown = [...selected.filter((name) => !options.includes(name)), ...options];

  useDismiss(open, containerRef, (restoreFocus) => {
    setOpen(false);
    if (restoreFocus) {
      triggerRef.current?.focus();
    }
  });

  // Reported in option order whatever order the boxes were ticked in, so one selection
  // is one URL.
  function toggle(name: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) {
      next.add(name);
    } else {
      next.delete(name);
    }
    onChange(shown.filter((option) => next.has(option)));
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
          className="input w-auto cursor-pointer"
          disabled={disabled}
          onClick={() => {
            setOpen((current) => !current);
          }}
        >
          <span>{summarize(selected)}</span>
        </button>
        {open && (
          // text-sm because daisyUI's fieldset writes 0.75rem; the labels carry none of
          // its label class, which dims a caption to 60% and these are the choices.
          <fieldset
            id="categories-panel"
            className="absolute top-full right-0 z-10 mt-2 flex w-max flex-col gap-1 rounded-box bg-base-100 p-2 text-sm shadow-lg"
          >
            <legend className="sr-only">Categories</legend>
            {shown.map((name) => (
              <label key={name} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm"
                  checked={selected.includes(name)}
                  onChange={(event) => {
                    toggle(name, event.target.checked);
                  }}
                />
                {name}
              </label>
            ))}
            {selected.length > 0 && (
              <button
                type="button"
                className="btn btn-ghost btn-sm text-sm font-normal"
                onClick={() => {
                  onChange([]);
                }}
              >
                Clear selection
              </button>
            )}
          </fieldset>
        )}
      </div>
    </FilterField>
  );
}
