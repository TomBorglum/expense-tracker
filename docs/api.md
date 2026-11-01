# The API

Every query parameter the four routes take.

## Asking for one currency

`?currency=` restates every expense in the code given, **replacing** `amount` and
`currency`, so the payload is the same shape either way. `1250.00 DKK` at `0.134048`
comes back as `"167.56" EUR`: `Decimal` arithmetic throughout, quantized to two places
with `ROUND_HALF_UP`, and still a string on the wire.

Only what `data/currencies/rates.tsv` states in that direction is used, each rate as the
file writes it. An expense already in the requested currency passes through untouched, so
the file holds no `DKK DKK 1.000000` row.

Anything else is a `422` carrying a plain-string `detail`, the same shape as the 503s
above:

| Request | Body |
| --- | --- |
| `?currency=CHF` | `{"detail": "no exchange rate from DKK to CHF"}` |
| `?currency=euro` | `{"detail": "currency must be an ISO 4217 code"}` |

A lowercase code is refused, matching the loaders, which refuse one in a file. One
unconvertible expense refuses the **whole** request, so every amount in a list stands in
one currency. A pair loaded twice is refused the same way, and only when that pair is
actually needed.

The arithmetic lives in `backend/src/expense_tracker/conversion.py`, which knows no HTTP
and holds no session - it takes records and rates and gives records back, so it is
tested in `backend/tests/test_conversion.py` without a client or a database.

## Asking for a range of dates

`?from_date=` and `?to_date=` narrow the list to the expenses dated between them.
**Both bounds are inclusive**, so `?from_date=2026-01-01&to_date=2026-01-31` is January
including both the 1st and the 31st, and **each is optional on its own**: give only
`from_date` and the range runs to the newest expense there is, give only `to_date` and it
runs from the oldest. Give neither and the request is the one that was there before the
parameters existed.

The filtering is a `WHERE` clause on `expense_date`, served by the
`expense_oldest_first_idx` index that was already there. **A range holding no expenses is
`200 {"items": []}`**, on the terms an empty table is. The two parameters compose with
`?currency=`, and the range is applied first, so an expense outside it needs no exchange
rate.

Dates are read as `YYYY-MM-DD`, the form the payload's own `date` field uses. Anything
else is a `422` carrying the same plain-string `detail`:

| Request | Body |
| --- | --- |
| `?from_date=01/01/2026` | `{"detail": "from_date must be a date in YYYY-MM-DD form"}` |
| `?to_date=2026-02-30` | `{"detail": "to_date must be a date in YYYY-MM-DD form"}` |
| `?from_date=2026-03-01&to_date=2026-01-01` | `{"detail": "from_date must not be after to_date"}` |

A range that ends before it begins is refused. That refusal belongs to the `DateRange`
type rather than to the parsing, so it holds however the range is built, and the
repository takes that type with its ordering already checked. Both live in
`backend/src/expense_tracker/date_range.py`, which knows no HTTP and no database at all,
and are tested in `backend/tests/test_date_range.py`.

## Asking for one or more categories

**Every value is a slug, never a category path.** A slug is the URL spelling of a
category - `going-out:jalsa-pool` for `Going Out:Jalsa+pool` - assigned once as the
expenses are loaded and sent on every payload that names a category; see
[Category slugs](#category-slugs).

`?category=` narrows the list to the expenses in the category whose slug it names. **The
key repeats once per value**, so `?category=food&category=housing` is every expense in
either, and a value given twice counts once. Give none and every category is included.

`?not_category=` is the same key read the other way: every expense **except** the ones in
the category named. The two compose, because a request states **where the selection
changes**: the root has a sign, each value flips a subtree, and **the longest slug over a
row decides**. So `?category=settlement` is the settlements alone,
`?not_category=settlement` is everything else, and
`?category=settlement&not_category=settlement:alice` is the settlements except hers. A
slug in both lists is refused: two flips of the same length over one node.

`?category_default=` is the root's own sign, `all` or `none`. Absent, it is `all` unless
`?category=` names a slug, in which case it is `none`: that is what keeps a request naming
categories meaning those and no others. The flag carries weight in two places -
`?category_default=none` alone, which selects **nothing** and is `200 {"items": []}`, and
`?category_default=all` beside both lists, which is everything but one subtree with a
branch of that subtree kept. A client that sends none of the three asks for every
category.

A value is matched the way the loader stored the slug: **stripped level by level, then
verbatim**, so `?category=%20food` is `food`, and every slug is lower case. That is the
loader's own strip, so the filter meets a stored value on the terms it was stored under,
and the case is the client's to send, as a currency code is.

**A value matches the node it names together with every node below it.** So
`?category=settlement` is every settlement and `?category=settlement:alice` is only
hers. Over categories that carry no path the two are the same thing.

The filtering is one `WHERE` clause beside the two date clauses - a join from
`expense.category` to the `category` table, then a `CASE` whose arms are the flips in
longest-slug order, each `= slug OR LIKE slug || ':%'`, falling through to the root's
sign. It composes with `?currency=`, `?from_date=` and `?to_date=` the way those compose
with each other: all three narrow the query, and the conversion runs over whatever they
left. The index behind it is `expense_oldest_first_idx`, which orders the scan over a
small table, while `category` carries one for the slug it is joined on and one for the
level the list is read by. **A category nobody has spent in is `200 {"items": []}`**, on
the terms an empty table is. A category is whatever a file said, and the filter is read
against the stored slugs alone.

`GET /api/expenses/categories` is that list: every category at the levels asked for,
**once each and in path order**, as `{"items": [{"category": "Settlement:Alice", "name":
"Alice", "slug": "settlement:alice", "parent": "Settlement", "parent_slug":
"settlement"}]}`. `name` is the path's last level and `parent` the path above it, so **no
client has to know what joins one level to the next**; a depth-1 category carries both
parent keys absent. `slug` is what the three filter parameters take and `parent_slug` is
the slug above it, so a client keys its own tree on the pair it sends and shows `name`,
the slugs arriving ready to use. The ordering is the repository's, `list_categories` in
`backend/src/expense_tracker/expense_repository.py`: the route reproduces the order it is
handed, as the other three do.

`?from_level=` and `?to_level=` choose the depths, both inclusive. **Absent, they are the
top level alone**, and an absent `to_level` is whatever `from_level` is, so
`?from_level=2` is exactly depth 2 while
`?to_level=3` is depths 1 through 3. The `category` table holds one row per node with its
own depth, so the range is a plain `WHERE level IN (...)`, and **an ancestor nobody filed
anything directly under is still listed**: `Settlement` appears even when every settlement
is `Settlement:<someone>`, the loader having written that row, which is what makes the
node selectable. `MAX_LEVEL` in
`backend/src/expense_tracker/level_range.py` bounds how many levels a client can name.
The cluster is `initdb --locale=C`, so name order is byte order - `Zoo` before `apple` -
which is the order Python's `sorted()` gives too. **An empty table is
`200 {"items": []}`** and an unreachable database
`503 {"detail": "expenses unavailable"}`, the same table answering the same way.

A blank value is a `422` carrying the same plain-string `detail`:

| Request | Body |
| --- | --- |
| `?category=` | `{"detail": "category must not be blank"}` |
| `?category=%20` | `{"detail": "category must not be blank"}` |
| `?not_category=` | `{"detail": "category must not be blank"}` |
| `?category=food&not_category=food` | `{"detail": "category both selected and deselected: food"}` |
| `?category_default=every` | `{"detail": "unknown category_default: every"}` |
| `?from_level=two` | `{"detail": "from_level must be a whole number"}` |
| `?from_level=0` | `{"detail": "from_level must be 1 or more"}` |
| `?to_level=11` | `{"detail": "to_level must not be more than 10"}` |
| `?from_level=3&to_level=2` | `{"detail": "from_level must not be after to_level"}` |

An empty value is malformed, as an empty `?from_date=` is, and blank means blank after
the strip, as it does to the loader. The refusal belongs to the `CategoryFilter` type
rather than to the parsing, so it holds however the filter is built, and the repository
takes that type. Both live
in `backend/src/expense_tracker/category_filter.py`, which knows no HTTP and no database
at all, and are tested in `backend/tests/test_category_filter.py`.

#### Category paths

A category is one `text` column holding a `:`-separated path - `Groceries`, or
`Settlement:Alice`. **Depth is unbounded and a third level needs no API change**, the
path being one column however deep it goes.

The separator is declared twice and only twice: `SEPARATOR` in `category_filter.py`, and
the `expense_category_is_a_path` CHECK in `schema.sql` that refuses an empty level. That
CHECK is what keeps **the separator out of every level**, so splitting a path or joining
one back up is lossless and **the levels need no escaping** in the SQL, the URL or the
payload. Matching is by level rather than by characters, which is why the clause has two
legs: `food` covers `food:dining` and leaves `foodstuffs` alone.

The storage is plain `text`, where the CHECK above makes a prefix match exact.
PostgreSQL's own `ltree` models the same shape, with labels that hold no space, and stays
the upgrade path if the table ever outgrows the scan.

#### Category slugs

A category path is what a file said, and a URL carries a spelling of its own.
`Going Out:Jalsa+pool` holds a space and a plus; percent-encoded, the address bar reads
`Going%20Out%3AJalsa%2Bpool`, and `+` is what `application/x-www-form-urlencoded` already
spells a space as. So the value a user reads and the value a URL carries part company:
every category also has a **slug**, and the slug is what the API takes and what the
frontend puts in the URL.

A slug holds `a-z`, `0-9`, `-` within a level and `:` between levels. The one character
in it a query escapes is the colon, which `frontend/src/router.ts` puts back, so a
category URL is free of percent signs. One level becomes one slug level
by lower-casing it, transliterating the three Danish letters (`ae`, `oe`, `aa`) and
stripping any other diacritic, then collapsing each run of anything left to a single `-`
and trimming the ends: `Jalsa & pool` is `jalsa-pool`, `100%` is `100`. A level that comes
out empty - punctuation alone, or letters no transliteration reaches - is refused while
loading, so every slug names one category.

Two siblings can want one slug, and the **second is numbered rather than refused**:
`Going Out` is `going-out` and `Going-Out` is `going-out-1`, with the next free number
taken, so a real `Going Out 1` beside them keeps `going-out-1` for itself and pushes the
collision to `going-out-2`. The numbering is **per sibling group**, a parent's own slug
already separating the branches, so upstream data stands as it is.

Which sibling gets the bare slug is decided by **order of first appearance in file-name
order, then by path within a file**, which makes the assignment a function of the loaded
files and nothing else. Two invariants follow, and both are checked rather than assumed:

- **The same files give the same slugs**, however they were loaded, so a link survives a
  `backend-db-reset` and a reload.
- **Loading a new file never changes a slug already assigned.** A later month sorts last
  and can only append.

**Backfilling** is the case the second invariant is enforced against - loading
`2024-01.yaml` after `2026-*.yaml`, where the earlier name sorts ahead of the slugs
already assigned. The loader recomputes every slug on every file, compares them with the
stored ones, and **refuses the file** if any would move, naming the category and both
slugs, on the same terms as any other file problem. The fix is a rebuild, the ordinary
path here anyway.

The slugs live in the `category` table, one row per node with its path, its slug, its
depth and the file it first appeared in - the ancestors included, since an ancestor's slug
is a component of every slug below it, and since a node nothing is filed directly under is
still selectable. `UNIQUE (slug)` sits behind the assignment as a backstop, which the
numbering keeps quiet; a violation is a bug in this project. `slug_level` is in
`category_filter.py` and `assign_slugs` in
`expense_loader.py`, both of which know no database; the tests are in
`backend/tests/test_category_filter.py` and `backend/tests/test_expense_loader.py`.

## Asking for totals

`GET /api/expenses/totals` sums the rows `/api/expenses` lists, over the period
`?period=` names. It takes the same `?currency=`, `?from_date=`, `?to_date=` and
`?category=` as the list does and means the same thing by each.

**`?period=` is required**, a grain being the caller's to choose; `month` is the only one,
so the payload field is the grain-neutral `period`. Rows are keyed by
`(period, currency)`, and `?group_by=category` adds a third part to that key.
**`currency` stays in the key whatever was asked for**, so every sum is in one currency.

**`?group_by=` is only a toggle: a row sums under the path its expenses carry.** The
difference between this endpoint and the list is the aggregation: a totals row names
exactly what an expenses row names. `?category=` narrows which rows arrive and chooses no
grain. Say Alice's settlement is 150 and Bob's is 25:

| Selection | Rows |
| --- | --- |
| nothing | `Settlement:Alice` 150, `Settlement:Bob` 25, and every other path |
| `Settlement` | `Settlement:Alice` 150, `Settlement:Bob` 25 |
| `Settlement` and `Settlement:Alice` | the same two rows |

The third one is worth reading twice: ticking an ancestor as well changes nothing, the
longest flip over a row deciding. The rows under a period still add to what the same
request returns ungrouped. **Depth belongs to the category list**, so a sum is always at
the grain its own rows carry.

The response is a **dense calendar**: one row per period from the oldest matching expense
to the newest, whether or not anything was spent in it. `period`, `from_date` and
`to_date` are on every row; `amount`, `currency` and `category` are present with a value
or **absent altogether**.

That absence carries meaning, and credits are why. A credit - a refund, a reimbursement,
a share paid back - is a negative expense, so a period can hold rows that cancel each
other out:

| Period | Rows in it | What comes back |
| --- | --- | --- |
| Nothing recorded | none | no `amount` key at all |
| `430.00` spent, `430.00` refunded | two | `"amount": "0.00"` |
| `150.00` refunded, nothing bought | one | `"amount": "-150.00"` |

An absent `amount` says "none recorded"; `"0.00"` says "these cancelled out", which is
what keeps a month of credits legible as one.

The conversion runs **before** the summing, and the order is the point: `?currency=`
quantizes each amount to cents, and converting then adding is what makes a total equal
what a reader adds up from `/api/expenses?currency=EUR`. That is why the summing lives in
`backend/src/expense_tracker/aggregation.py` in Python, over the rows `list_expenses`
returns. A bad `period` or `group_by` is a `422` carrying the same plain-string `detail`
as the refusals above.

## The range average

**The body carries a `summary` beside `items`**: one entry per currency, each naming that
currency and `average`, the mean of its period totals over the whole calendar the rows
span. It is what the totals view shows above the table, and answers "what does a month
cost" across the range.

```json
{
  "items": [{"period": "2026-01", "amount": "3498.56", "currency": "DKK", "...": "..."}],
  "summary": [{"currency": "DKK", "average": "3443.07"}]
}
```

**Both keys are always present.** An entry exists only for a currency that has expenses,
so `exclude_none` has nothing to drop here. A currency's entry is where a figure about the
whole range lives.

**The divisor is the same calendar the rows walk** - first matching expense to last, with
interior gaps counted - so a month nobody spent in pulls the figure down. A range filtered
wider than the data divides by the data, which is why the number can differ from what the
requested bounds suggest.

**It is the same whether or not `?group_by=` was sent.** Grouping re-keys the rows without
changing which expenses they sum, so both bodies carry an identical summary and a client
can read it from either. `test_the_range_summary_is_the_same_grouped_or_not` pins it on
both sides of the route. The quantization is a conversion's: `ROUND_HALF_UP` to cents, and
a cumulative credit too small to show at that scale is normalised from `-0.00` to `0.00`.

**No expenses means an empty summary**, the same `200` an empty `items` is: an empty
extent is an empty calendar, so there is nothing to average.

All four endpoints are read-only over HTTP. Rows arrive through
`pixi run backend-load-expenses` and `pixi run backend-load-currencies`, which is the
whole write path.

Those four routes are the whole surface: the frontend is a separate app, and the API
publishes no OpenAPI schema, `/docs` or `/redoc`. `backend/tests/test_app.py` asserts that
`/`, `/static/*`, any other `/api` path and the three docs routes all return 404, which is
what holds the surface at four.
