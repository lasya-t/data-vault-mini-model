"""Data Vault 2.0 in DuckDB: hubs, links, satellites, loaded insert-only.

hub_customer         one row per business key (customer_number), from any source
hub_account          one row per account_id
link_customer_account   which accounts belong to which customer
sat_customer_crm     customer attributes from CRM, a new row only when they change (hashdiff)
sat_account_billing  plan and price per account, same rule

Hash keys are MD5 of the cleaned business key, so every system computes the same key for
the same customer with no lookups. Nothing is ever updated or deleted: history is kept by design.
"""
from __future__ import annotations

import duckdb
import pandas as pd

DDL = """
CREATE TABLE IF NOT EXISTS hub_customer (hk_customer VARCHAR PRIMARY KEY, customer_number VARCHAR,
                                         load_date DATE, record_source VARCHAR);
CREATE TABLE IF NOT EXISTS hub_account (hk_account VARCHAR PRIMARY KEY, account_id VARCHAR,
                                        load_date DATE, record_source VARCHAR);
CREATE TABLE IF NOT EXISTS link_customer_account (hk_customer_account VARCHAR PRIMARY KEY, hk_customer VARCHAR,
                                                  hk_account VARCHAR, load_date DATE, record_source VARCHAR);
CREATE TABLE IF NOT EXISTS sat_customer_crm (hk_customer VARCHAR, load_date DATE, hashdiff VARCHAR,
                                             name VARCHAR, email VARCHAR, state VARCHAR, record_source VARCHAR,
                                             PRIMARY KEY (hk_customer, load_date));
CREATE TABLE IF NOT EXISTS sat_account_billing (hk_account VARCHAR, load_date DATE, hashdiff VARCHAR,
                                                plan VARCHAR, monthly_price DECIMAL(8,2), record_source VARCHAR,
                                                PRIMARY KEY (hk_account, load_date));
"""


def bk(col: str) -> str:
    """Business-key cleaning: the same customer must hash the same in every system."""
    return f"upper(trim({col}))"


def hk(*cols: str) -> str:
    return "md5(" + " || '||' || ".join(bk(c) for c in cols) + ")"


def hashdiff(*cols: str) -> str:
    return "md5(" + " || '||' || ".join(f"coalesce(CAST({c} AS VARCHAR), '')" for c in cols) + ")"


def _insert_hub(con, table, key_col, hk_col, src_view, source, day):
    con.execute(f"""
        INSERT INTO {table}
        SELECT DISTINCT {hk(key_col)}, {bk(key_col)}, DATE '{day}', '{source}' FROM {src_view} s
        WHERE {hk(key_col)} NOT IN (SELECT {hk_col} FROM {table})
    """)


def _insert_sat(con, table, hk_expr, hk_col, attrs, src_view, source, day):
    # insert only when the attributes differ from the latest satellite row for that key
    a = ", ".join(attrs)
    con.execute(f"""
        INSERT INTO {table}
        SELECT s.hk, DATE '{day}', s.hd, {', '.join('s.' + x for x in attrs)}, '{source}'
        FROM (SELECT DISTINCT {hk_expr} AS hk, {hashdiff(*attrs)} AS hd, {a} FROM {src_view}) s
        LEFT JOIN (
            SELECT {hk_col}, hashdiff FROM {table}
            QUALIFY row_number() OVER (PARTITION BY {hk_col} ORDER BY load_date DESC) = 1
        ) cur ON cur.{hk_col} = s.hk
        WHERE cur.hashdiff IS DISTINCT FROM s.hd
          AND NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{hk_col} = s.hk AND t.load_date = DATE '{day}')
    """)


def load_day(con: duckdb.DuckDBPyConnection, day: str, crm: pd.DataFrame, billing: pd.DataFrame) -> dict:
    con.execute(DDL)
    before = counts(con)
    con.register("stg_crm", crm)
    con.register("stg_billing", billing)
    con.execute("BEGIN")
    _insert_hub(con, "hub_customer", "customer_number", "hk_customer", "stg_crm", "crm", day)
    _insert_hub(con, "hub_customer", "customer_number", "hk_customer", "stg_billing", "billing", day)
    _insert_hub(con, "hub_account", "account_id", "hk_account", "stg_billing", "billing", day)
    con.execute(f"""
        INSERT INTO link_customer_account
        SELECT DISTINCT {hk('customer_number', 'account_id')}, {hk('customer_number')}, {hk('account_id')},
               DATE '{day}', 'billing'
        FROM stg_billing
        WHERE {hk('customer_number', 'account_id')} NOT IN (SELECT hk_customer_account FROM link_customer_account)
    """)
    _insert_sat(con, "sat_customer_crm", hk("customer_number"), "hk_customer", ["name", "email", "state"], "stg_crm", "crm", day)
    _insert_sat(con, "sat_account_billing", hk("account_id"), "hk_account", ["plan", "monthly_price"], "stg_billing", "billing", day)
    con.execute("COMMIT")
    con.unregister("stg_crm")
    con.unregister("stg_billing")
    after = counts(con)
    return {t: after[t] - before.get(t, 0) for t in after}


def counts(con) -> dict:
    tables = ["hub_customer", "hub_account", "link_customer_account", "sat_customer_crm", "sat_account_billing"]
    existing = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    return {t: con.execute(f"SELECT count(*) FROM {t}").fetchall()[0][0] if t in existing else 0 for t in tables}
