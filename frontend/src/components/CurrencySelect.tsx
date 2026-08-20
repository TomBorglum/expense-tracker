interface CurrencySelectProps {
  readonly value: string;
  readonly options: readonly string[];
  readonly disabled: boolean;
  readonly onChange: (currency: string) => void;
}

// The control that picks the currency the expenses are restated in. It holds no state
// and makes no request: the value is the URL's, and the options are the codes the loaded
// rate table can reach.
export function CurrencySelect({
  value,
  options,
  disabled,
  onChange,
}: CurrencySelectProps) {
  // A value nobody offered still gets an option, because a select whose value matches no
  // option shows the first one instead - which would disagree with both the URL and the
  // request in flight. That is reachable by typing a code into the address bar.
  const shown = options.includes(value) ? options : [value, ...options];

  return (
    <div className="flex items-center gap-3">
      {/* A real label rather than aria-label: the select needs a visible name here, and
          an associated one is what gives it an accessible name for free. */}
      <label htmlFor="currency" className="text-sm text-base-content/60">
        Currency
      </label>
      <select
        id="currency"
        className="select select-bordered select-sm"
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {shown.map((code) => (
          <option key={code} value={code}>
            {code}
          </option>
        ))}
      </select>
    </div>
  );
}
