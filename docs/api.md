# The API

The route table is in [README.md](../README.md#routes). Every query parameter those four
routes take is below.

## Asking for one currency

`?currency=` restates every expense in the code given, **replacing** `amount` and
`currency`. `1250.00 DKK` at `0.134048` comes back as `"167.56" EUR`: `Decimal` arithmetic
throughout, quantized to two places with `ROUND_HALF_UP`, and still a string on the wire.

Only what `data/currencies/rates.tsv` states in that direction is used. An expense already
in the requested currency passes through untouched, so the file holds no `DKK DKK
1.000000` row.

| Request | `detail` |
| --- | --- |
| `?currency=CHF` | `no exchange rate from DKK to CHF` |
| `?currency=euro` | `currency must be an ISO 4217 code` |

A lowercase code is refused, matching the loaders. **One unconvertible expense refuses
the whole request**, so every amount in a list stands in one currency. A pair loaded twice
is refused on the same terms, and only when that pair is needed.

## Asking for a range of dates

`?from_date=` and `?to_date=` narrow the list to the expenses dated between them. **Both
bounds are inclusive**, and **each is optional on its own**: give only `from_date` and the
range runs to the newest expense there is, give only `to_date` and it runs from the
oldest.

The range is applied **before** `?currency=`. Dates are read as `YYYY-MM-DD`, the form
the payload's own `date` field uses.

| Request | `detail` |
| --- | --- |
| `?from_date=01/01/2026` | `from_date must be a date in YYYY-MM-DD form` |
| `?to_date=2026-02-30` | `to_date must be a date in YYYY-MM-DD form` |
| `?from_date=2026-03-01&to_date=2026-01-01` | `from_date must not be after to_date` |

## Asking for one or more categories

**Every value is a slug, never a category path.** See [Category slugs](#category-slugs).

`?category=` narrows the list to the expenses in the category whose slug it names. **The
key repeats once per value**, so `?category=food&category=housing` is every expense in
either, and a value given twice counts once. **A value matches the node it names together
with every node below it**: `?category=settlement` is every settlement,
`?category=settlement:alice` only hers.

`?not_category=` is the same key read the other way. The two compose, because a request
states **where the selection changes**: the root has a sign, each value flips a subtree,
and **the longest slug over a row decides**. So `?not_category=settlement` is everything
else, and `?category=settlement&not_category=settlement:alice` is the settlements except
hers. A slug in both lists is refused, being two flips of the same length over one node.

`?category_default=` is the root's own sign, `all` or `none`. **Absent, it is `all` unless
`?category=` names a slug, in which case it is `none`**, which is what keeps a request
naming categories meaning those and no others. It changes the answer in two cases:
`?category_default=none` alone selects **nothing**, and `?category_default=all` beside
both lists is everything but one subtree with a branch of that subtree kept.

A value is matched the way the loader stored the slug, **stripped level by level, then
verbatim**, so `?category=%20food` is `food`, and every slug is lower case. The case is
the client's to send, as a currency code is. **A category nobody has spent in is `200
{"items": []}`**, on the terms an empty table is.

`GET /api/expenses/categories` is the category list: every category at the levels asked
for, **once each and in path order**, as `{"items": [{"category": "Settlement:Alice",
"name": "Alice", "slug": "settlement:alice", "parent": "Settlement", "parent_slug":
"settlement"}]}`. `name` is the path's last level and `parent` the path above it, so **no
client has to know what joins one level to the next**; a depth-1 category carries both
parent keys absent. `slug` is what the three filter parameters take and `parent_slug` the
slug above it, so a client keys its own tree on the pair it sends and shows `name`.

`?from_level=` and `?to_level=` choose the depths, both inclusive. **Absent, they are the
top level alone**, and an absent `to_level` is whatever `from_level` is, so
`?from_level=2` is exactly depth 2 while `?to_level=3` is depths 1 through 3. **An
ancestor nobody filed anything directly under is still listed**, so `Settlement` appears
even when every settlement is `Settlement:<someone>`, which is what makes the node
selectable. `MAX_LEVEL` in `backend/src/expense_tracker/level_range.py` bounds how many
levels a client can name. The cluster is `initdb --locale=C`, so name order is byte order:
`Zoo` before `apple`.

| Request | `detail` |
| --- | --- |
| `?category=` | `category must not be blank` |
| `?category=%20` | `category must not be blank` |
| `?not_category=` | `category must not be blank` |
| `?category=food&not_category=food` | `category both selected and deselected: food` |
| `?category_default=every` | `unknown category_default: every` |
| `?from_level=two` | `from_level must be a whole number` |
| `?from_level=0` | `from_level must be 1 or more` |
| `?to_level=11` | `to_level must not be more than 10` |
| `?from_level=3&to_level=2` | `from_level must not be after to_level` |

### Category paths

A category is one `text` column holding a `:`-separated path, `Groceries` or
`Settlement:Alice`. **Depth is unbounded and a third level needs no API change.**

The separator is declared twice and only twice: `SEPARATOR` in `category_filter.py`, and
the `expense_category_is_a_path` CHECK in `schema.sql` that refuses an empty level. That
CHECK keeps **the separator out of every level**, so **the levels need no escaping**.
Matching is by level rather than by characters, which is why `food` covers `food:dining`
and leaves `foodstuffs` alone.

### Category slugs

Every category also has a **slug**, and the slug is what the API takes and what the
frontend puts in the URL.

A slug holds `a-z`, `0-9`, `-` within a level and `:` between levels. The one character a
query escapes is the colon, which `frontend/src/router.ts` puts back, so a category URL is
free of percent signs. One level becomes one slug level by lower-casing it,
transliterating the three Danish letters (`ae`, `oe`, `aa`) and stripping any other
diacritic, then collapsing each run of anything left to a single `-` and trimming the
ends: `Jalsa & pool` is `jalsa-pool`, `100%` is `100`. **A level that comes out empty is
refused while loading**, so every slug names one category.

Two siblings can want one slug, and the **second is numbered rather than refused**:
`Going Out` is `going-out` and `Going-Out` is `going-out-1`, with the next free number
taken, so a real `Going Out 1` beside them keeps `going-out-1` and pushes the collision to
`going-out-2`. The numbering is **per sibling group**. Which sibling gets the bare slug is
decided by **order of first appearance in file-name order, then by path within a file**.
Two invariants follow, both checked rather than assumed:

- **The same files give the same slugs**, however they were loaded, so a link survives a
  `backend-db-reset` and a reload.
- **Loading a new file never changes a slug already assigned.** A later month sorts last
  and can only append.

**Backfilling** is the case the second is enforced against: loading `2024-01.yaml` after
`2026-*.yaml`, where the earlier name sorts ahead of the slugs already assigned. The
loader recomputes every slug on every file, compares them with the stored ones, and
**refuses the file** if any would move, naming the category and both slugs. The fix is a
rebuild.

## Asking for totals

`GET /api/expenses/totals` sums the rows `/api/expenses` lists, over the period `?period=`
names. It takes the same `?currency=`, `?from_date=`, `?to_date=` and `?category=` as the
list does and means the same thing by each.

**`?period=` is required**, a grain being the caller's to choose; `month` is the only one,
so the payload field is the grain-neutral `period`. Rows are keyed by `(period,
currency)`, and `?group_by=category` adds a third part to that key. **`currency` stays in
the key whatever was asked for**, so every sum is in one currency.

**`?group_by=` is only a toggle: a row sums under the path its expenses carry.** A
totals row names exactly what an expenses row names, and `?category=` narrows which rows
arrive and chooses no grain. Say Alice's settlement is 150 and Bob's is 25:

| Selection | Rows |
| --- | --- |
| nothing | `Settlement:Alice` 150, `Settlement:Bob` 25, and every other path |
| `Settlement` | `Settlement:Alice` 150, `Settlement:Bob` 25 |
| `Settlement` and `Settlement:Alice` | the same two rows |

Ticking an ancestor as well changes nothing, the longest flip over a row deciding. The
rows under a period still add to what the same request returns ungrouped.

The response is a **dense calendar**: one row per period from the oldest matching expense
to the newest, whether or not anything was spent in it. `period`, `from_date` and
`to_date` are on every row; `amount`, `currency` and `category` are present with a value
or **absent altogether**. That absence carries meaning, because a credit is a negative
expense and a period can hold rows that cancel out:

| Period | Rows in it | What comes back |
| --- | --- | --- |
| Nothing recorded | none | no `amount` key at all |
| `430.00` spent, `430.00` refunded | two | `"amount": "0.00"` |
| `150.00` refunded, nothing bought | one | `"amount": "-150.00"` |

An absent `amount` says "none recorded"; `"0.00"` says "these cancelled out".

**The conversion runs before the summing**, `?currency=` quantizing each amount to
cents, so a total equals what a reader adds up from `/api/expenses?currency=EUR`.

## The range average

**The body carries a `summary` beside `items`**: one entry per currency, each naming
that currency and `average`, the mean of its period totals over the whole calendar the
rows span.

```json
{
  "items": [{"period": "2026-01", "amount": "3498.56", "currency": "DKK", "...": "..."}],
  "summary": [{"currency": "DKK", "average": "3443.07"}]
}
```

**Both keys are always present**, and an entry exists only for a currency that has
expenses.

**The divisor is the same calendar the rows walk**, first matching expense to last,
with interior gaps counted, so a month nobody spent in pulls the figure down. A range
filtered wider than the data divides by the data.

**It is the same whether or not `?group_by=` was sent.** The quantization is a
conversion's: `ROUND_HALF_UP` to cents, and a cumulative credit too small to show at that
scale is normalised from `-0.00` to `0.00`. **No expenses means an empty summary.**

Those four routes are the whole surface, all read-only: rows arrive through `pixi run
backend-load-expenses` and `pixi run backend-load-currencies`, and the API publishes no
OpenAPI schema, `/docs` or `/redoc`.
