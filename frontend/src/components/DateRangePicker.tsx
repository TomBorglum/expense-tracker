import { type DateRange, DayPicker, getDefaultClassNames } from "@daypicker/react";
import { useEffect, useRef, useState } from "react";

import {
  addMonths,
  calendarBounds,
  fromIsoDate,
  startOfMonth,
  toIsoDate,
} from "../dates";
import { FilterField } from "./FilterField";

const defaultClassNames = getDefaultClassNames();

// What the two panels are handed beyond daisyUI's `react-day-picker` theme.
//
// `today` is emptied to drop the modifier: getClassNamesForModifiers keeps only truthy
// entries, so the day carries no rdp-today and daisyUI's filled primary block - four
// classes against selected's three, so it beats the range it sits inside - never lands.
// This control reports a from date and a to date, and a third marked day reads as picked.
//
// The dropdowns are real <select>s, and daisyUI leaves them transparent because they sit
// invisible over the caption. A browser paints a native popup from the control's own
// colours, so a transparent one comes up on white while still taking the inherited text
// colour - unreadable under dim. The options carry it too, because the select's colour
// alone does not reach them in every browser.
//
// daisyUI writes the calendar at 0.75rem; text-sm brings it to the 0.875rem the controls,
// the captions and the table use. Four names carry it: the ordinary day numbers follow the
// root through `font: inherit` and the dropdowns are transparent over the caption, but a
// selected day is sized by the theme again and would shrink when it was picked.
const dayPickerClassNames = {
  today: "",
  dropdown: `${defaultClassNames.dropdown} bg-base-100 text-base-content [&>option]:bg-base-100`,
  month_caption: `${defaultClassNames.month_caption} text-sm`,
  weekday: `${defaultClassNames.weekday} text-sm`,
  selected: `${defaultClassNames.selected} text-sm`,
};

interface DateRangePickerProps {
  readonly from: string;
  readonly to: string;
  readonly onChange: (from: string, to: string) => void;
}

interface Shown {
  left: Date;
  right: Date;
}

function clamp(month: Date, start: Date, end: Date): Date {
  if (month.getTime() < start.getTime()) {
    return start;
  }
  return month.getTime() > end.getTime() ? end : month;
}

// The month each panel opens on: the one the range starts in, and the one it ends in.
// A range inside a single month puts the right panel on the month after, so the two
// never duplicate unless the upper bound leaves nowhere else to go.
function shownFor(from: string, to: string): Shown {
  const bounds = calendarBounds();
  const start = startOfMonth(bounds.start);
  const end = startOfMonth(bounds.end);
  const opening = fromIsoDate(from) ?? new Date();
  const left = clamp(startOfMonth(opening), start, end);
  const closing = fromIsoDate(to);
  const right = closing === undefined ? left : clamp(startOfMonth(closing), start, end);
  return right.getTime() > left.getTime()
    ? { left, right }
    : { left, right: clamp(addMonths(left, 1), start, end) };
}

// The days the expenses are drawn from, as the two YYYY-MM-DD strings the API reads. A
// value the backend would refuse is shown as it stands rather than corrected, the way
// CurrencySelect shows a code it was given.
export function DateRangePicker({ from, to, onChange }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  // Holds the half-built range between the two clicks. Null while the calendar agrees
  // with the URL, which is what makes the props the source of truth the rest of the time.
  const [picked, setPicked] = useState<DateRange | null>(null);
  const [shown, setShown] = useState<Shown>(() => shownFor(from, to));
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = picked ?? { from: fromIsoDate(from), to: fromIsoDate(to) };
  const bounds = calendarBounds();

  // Dismissal drops a half-picked range rather than keeping it: the URL still holds the
  // range that was there, and a calendar disagreeing with the trigger is worse than
  // losing one click. Listeners live on the document because the alternative is a
  // keydown handler on a non-interactive div (sonar S6847).
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function dismiss(restoreFocus: boolean) {
      setOpen(false);
      setPicked(null);
      if (restoreFocus) {
        triggerRef.current?.focus();
      }
    }
    function handlePointerDown(event: PointerEvent) {
      // The trigger is inside the container, so its own click only ever toggles below.
      if (!containerRef.current?.contains(event.target as Node)) {
        dismiss(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        dismiss(true);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function handleSelect(next: DateRange | undefined) {
    if (next?.from && next.to) {
      setPicked(null);
      setOpen(false);
      onChange(toIsoDate(next.from), toIsoDate(next.to));
      return;
    }
    // Only a start so far. Reporting it would put an open-ended range in the URL, and
    // the backend reads an empty bound as malformed rather than as no bound.
    setPicked(next ?? null);
  }

  // The panel a dropdown moved wins, and the other follows only far enough to stay in
  // order - so the left year can be changed without dragging the right along with it.
  function showLeft(month: Date) {
    setShown((current) => ({
      left: month,
      right: month.getTime() > current.right.getTime() ? month : current.right,
    }));
  }

  function showRight(month: Date) {
    setShown((current) => ({
      left: month.getTime() < current.left.getTime() ? month : current.left,
      right: month,
    }));
  }

  return (
    <FilterField label="Dates" labelId="date-range-label">
      {/* Positioned by hand rather than with daisyUI's dropdown classes. Those hide
          .dropdown-content until :focus-within or :popover-open, which fights a panel
          whose open state is React's - the calendar would vanish the moment focus left
          it while still mounted. The panel needs w-max because an absolute box
          shrink-wraps to one month. jsdom evaluates no CSS, so no test sees either.

          This div is also what an outside click is measured against, so it holds the
          trigger and the panel and nothing else: a click on the caption FilterField
          renders is outside the control and dismisses it. */}
      <div ref={containerRef} className="relative">
        {/* Labelled by the caption and by itself, so the accessible name carries both
            the control's purpose and the range it currently shows. */}
        <button
          id="date-range-value"
          ref={triggerRef}
          type="button"
          aria-expanded={open}
          aria-labelledby="date-range-label date-range-value"
          className="input w-auto cursor-pointer tabular-nums"
          onClick={() => {
            if (open) {
              setOpen(false);
              setPicked(null);
              return;
            }
            // Recomputed on every opening, so the panels always start on the range the
            // URL currently holds rather than wherever they were left.
            setShown(shownFor(from, to));
            setPicked(null);
            setOpen(true);
          }}
        >
          <span>
            {from} to {to}
          </span>
        </button>
        {open && (
          <div className="absolute top-full right-0 z-10 mt-2 flex w-max gap-2 rounded-box bg-base-100 p-2 shadow-lg">
            {/* Two calendars rather than one showing two months: numberOfMonths keeps
                the pair consecutive, and these navigate independently. They share
                `selected` and `onSelect`, so a range can start in either and end in the
                other. resetOnSelect, because the range arriving from the URL is always
                complete - without it a click would drag one end instead of starting
                over. Neither it nor addToRange can produce a range that ends before it
                begins, so the ordering needs no guard.

                startMonth and endMonth are what the year dropdown lists; with the
                arrows hidden, that list is the whole of what bounds navigation. */}
            <DayPicker
              className="react-day-picker text-sm"
              classNames={dayPickerClassNames}
              mode="range"
              resetOnSelect
              hideNavigation
              captionLayout="dropdown"
              reverseYears
              startMonth={bounds.start}
              endMonth={bounds.end}
              month={shown.left}
              onMonthChange={showLeft}
              selected={selected}
              onSelect={handleSelect}
            />
            <DayPicker
              className="react-day-picker text-sm"
              classNames={dayPickerClassNames}
              mode="range"
              resetOnSelect
              hideNavigation
              captionLayout="dropdown"
              reverseYears
              startMonth={bounds.start}
              endMonth={bounds.end}
              month={shown.right}
              onMonthChange={showRight}
              selected={selected}
              onSelect={handleSelect}
            />
          </div>
        )}
      </div>
    </FilterField>
  );
}
