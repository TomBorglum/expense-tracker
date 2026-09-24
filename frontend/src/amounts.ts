/** How an amount from the API is shown: spending unsigned, a credit as +. */

export const CREDIT_CLASS = "text-success";

const NEGATIVE_ZERO = /^-0(\.0+)?$/;

export interface DisplayAmount {
  readonly text: string;
  readonly isCredit: boolean;
}

// Works on the string alone and never builds a Number, so the cents are the backend's.
export function displayAmount(amount: string): DisplayAmount {
  if (NEGATIVE_ZERO.test(amount)) {
    return { text: amount.slice(1), isCredit: false };
  }
  if (amount.startsWith("-")) {
    return { text: `+${amount.slice(1)}`, isCredit: true };
  }
  return { text: amount, isCredit: false };
}
