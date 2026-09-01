import { FilterField } from "./FilterField";

interface CategoryToggleProps {
  readonly checked: boolean;
  readonly onChange: (byCategory: boolean) => void;
}

// The control that splits each period's total by category. It holds no state and makes no
// request: the value is the URL's, and it is off there by being absent, which is what the
// backend's group_by means by its own absence.
export function CategoryToggle({ checked, onChange }: CategoryToggleProps) {
  return (
    // A real label rather than aria-label, like the currency select: a checkbox takes one,
    // and an associated label is what names it for free.
    <FilterField label="By category" htmlFor="by-category">
      <input
        id="by-category"
        type="checkbox"
        className="toggle"
        checked={checked}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
    </FilterField>
  );
}
