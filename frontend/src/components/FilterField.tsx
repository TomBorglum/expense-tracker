import { type ReactNode } from "react";

// Exactly one of htmlFor and labelId, because the two filters name their controls
// differently and have to: a <select> takes a real <label htmlFor>, while a <button>
// cannot - a <label> does not name one - so the range trigger gets a <span id> for its
// own aria-labelledby to point at.
type FilterFieldProps = {
  readonly label: string;
  readonly children: ReactNode;
} & (
  | { readonly htmlFor: string; readonly labelId?: undefined }
  | { readonly labelId: string; readonly htmlFor?: undefined }
);

// The shell the filters above the table share: a caption beside the control it names.
// One place owns the gap and the caption's type, so the two cannot drift apart.
export function FilterField({ label, children, htmlFor, labelId }: FilterFieldProps) {
  const caption = "text-sm text-base-content/60";
  return (
    <div className="flex items-center gap-2">
      {htmlFor === undefined ? (
        <span id={labelId} className={caption}>
          {label}
        </span>
      ) : (
        <label htmlFor={htmlFor} className={caption}>
          {label}
        </label>
      )}
      {children}
    </div>
  );
}
