/** Conversion between a Date and the bare YYYY-MM-DD the API reads and writes. */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function pad(value: number, width = 2): string {
  return String(value).padStart(width, "0");
}

// Built from the local getters rather than toISOString(), which converts to UTC first and
// so names the previous day everywhere east of Greenwich.
export function toIsoDate(date: Date): string {
  return `${pad(date.getFullYear(), 4)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Undefined rather than a throw or an Invalid Date: validateSearch hands on whatever the
// URL carries, so the picker has to survive ?from_date=yesterday.
export function fromIsoDate(value: string): Date | undefined {
  if (!ISO_DATE.test(value)) {
    return undefined;
  }
  const date = new Date(
    Number(value.slice(0, 4)),
    Number(value.slice(5, 7)) - 1,
    Number(value.slice(8, 10)),
  );
  // Rejects a day the month does not have, and a year the two-digit window would shift.
  return toIsoDate(date) === value ? date : undefined;
}

export function currentMonth(): { from: string; to: string } {
  const today = new Date();
  return {
    from: toIsoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    // Day zero of the next month is the last day of this one.
    to: toIsoDate(new Date(today.getFullYear(), today.getMonth() + 1, 0)),
  };
}
