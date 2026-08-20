import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CurrencySelect } from "@/components/CurrencySelect";

function options() {
  return screen.getAllByRole<HTMLOptionElement>("option").map((option) => option.value);
}

test("offers the codes it was given, in that order", () => {
  render(
    <CurrencySelect
      value="DKK"
      options={["DKK", "EUR", "USD"]}
      disabled={false}
      onChange={vi.fn()}
    />,
  );
  // Named through its <label>, not an aria-label, which is what makes this query work.
  const select = screen.getByRole<HTMLSelectElement>("combobox", { name: "Currency" });
  expect(select.value).toBe("DKK");
  expect(options()).toEqual(["DKK", "EUR", "USD"]);
});

test("reports the code that was picked", async () => {
  const onChange = vi.fn();
  render(
    <CurrencySelect
      value="DKK"
      options={["DKK", "EUR", "USD"]}
      disabled={false}
      onChange={onChange}
    />,
  );
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "Currency" }),
    "EUR",
  );
  expect(onChange.mock.calls).toEqual([["EUR"]]);
});

test("is disabled when told to be", () => {
  render(<CurrencySelect value="DKK" options={["DKK"]} disabled onChange={vi.fn()} />);
  const select = screen.getByRole<HTMLSelectElement>("combobox", { name: "Currency" });
  expect(select.disabled).toBe(true);
});

test("shows a value nobody offered rather than silently picking another", () => {
  // Reachable by typing a code into the address bar: the URL is passed to the backend
  // unchecked, so the control has to agree with the request that is in flight.
  render(
    <CurrencySelect
      value="CHF"
      options={["DKK", "EUR"]}
      disabled={false}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByRole<HTMLSelectElement>("combobox", { name: "Currency" });
  expect(select.value).toBe("CHF");
  expect(options()).toEqual(["CHF", "DKK", "EUR"]);
});
