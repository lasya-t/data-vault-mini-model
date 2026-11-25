# data-vault-mini-model

A small Data Vault 2.0 model in DuckDB. Two source systems (a CRM and a billing system) both know about
customers. Their daily extracts are loaded insert-only into hubs, a link and satellites over three days of
changes, and a point-in-time table plus an as-of view sit on top for querying.

## Model

| Table | Holds | Key |
|---|---|---|
| `hub_customer` | one row per customer number, from either source | `hk_customer = md5(upper(trim(customer_number)))` |
| `hub_account` | one row per billing account | `hk_account` |
| `link_customer_account` | which customer owns which account | hash of both keys |
| `sat_customer_crm` | name, email, state — a new row only when something changed | `hk_customer, load_date` |
| `sat_account_billing` | plan and monthly price | `hk_account, load_date` |
| `pit_customer` | for each customer and snapshot date, which CRM row was current | built from the satellites |
| `customer_accounts_asof` (view) | profile + account count + monthly revenue per customer per date | |

Change detection uses a `hashdiff` over the descriptive columns, so a full extract that re-sends unchanged rows
adds nothing.

## What the three days contain

- **Day 1** – three CRM customers, two billing accounts.
- **Day 2** – Raj moves NJ → PA, Ana is re-sent unchanged, Omar (C004) is new, Ana upgrades Basic → Unlimited, Mei gets an account.
- **Day 3** – Ana arrives as `"c001 "` (lowercase, trailing space), Mei changes email, Omar opens two accounts,
  and billing sends account A50 for customer **C005**, whom the CRM has never sent.

## Results (`python -m vault.demo`)

Rows inserted per table (hub_customer, hub_account, link, sat_crm, sat_billing):

| Load | Inserted |
|---|---|
| 2025-03-01 | 3, 2, 2, 3, 2 |
| 2025-03-02 | 1, 1, 1, 2, 2 |
| 2025-03-03 | 1, 3, 3, 1, 3 |
| replay of each day again | 0 everywhere |

Final sizes: 5 customers, 6 accounts, 6 links, 6 CRM satellite rows, 7 billing satellite rows.

- `"c001 "` resolves to the existing C001 hub row, so it doesn't create a duplicate customer.
- C005 gets a hub row from billing alone. In the as-of view it shows up with an account and revenue but no
  name, flagged `missing_crm_profile = true`, so the gap is visible and the customer isn't lost.
- The view answers history questions directly: Raj is NJ on 03-01 and PA from 03-02; Omar has 2 accounts and
  135.00/month on 03-03.

## A bug the tests caught

The first satellite loader compared each incoming row with the *latest* satellite row. Replaying day 1 after
day 3 then saw Mei's old email as "different from current" and inserted it again as a new version, which
corrupted her history. The loader now compares with the latest row **on or before the load date**, and skips a
load date that is already present. `test_out_of_order_replay_of_old_day` covers it.

## Run

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m vault.demo
pytest -q
```

## Layout

```
src/vault/sources.py   three days of CRM and billing extracts
src/vault/model.py     DDL, hash keys, hub/link/satellite loaders
src/vault/marts.py     PIT table and as-of view
src/vault/demo.py      end-to-end run
tests/                 8 tests
```
