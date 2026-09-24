import { expect, test } from "vitest";

import { displayAmount } from "@/amounts";

test("shows spending as it arrives, unsigned", () => {
  expect(displayAmount("13.37")).toEqual({ text: "13.37", isCredit: false });
});

test("shows a negative amount as a credit with a plus sign", () => {
  expect(displayAmount("-4.20")).toEqual({ text: "+4.20", isCredit: true });
});

test("keeps every digit of a credit rather than parsing it", () => {
  // A float round trip would be where a cent could drift.
  expect(displayAmount("-12345678901234.99")).toEqual({
    text: "+12345678901234.99",
    isCredit: true,
  });
});

test("shows zero as zero, never as a credit", () => {
  expect(displayAmount("0.00")).toEqual({ text: "0.00", isCredit: false });
  expect(displayAmount("-0.00")).toEqual({ text: "0.00", isCredit: false });
});
