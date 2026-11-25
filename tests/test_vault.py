import duckdb
import pytest

from vault.marts import build_pit, create_views
from vault.model import counts, hk, load_day
from vault.sources import CRM, billing, crm

DAYS = list(CRM)


@pytest.fixture
def con():
    c = duckdb.connect()
    for d in DAYS:
        load_day(c, d, crm(d), billing(d))
    return c


def test_hash_key_ignores_case_and_spaces():
    c = duckdb.connect()
    messy, clean = hk("'c001 '"), hk("'C001'")
    a = c.execute(f"SELECT {messy}").fetchone()[0]
    b = c.execute(f"SELECT {clean}").fetchone()[0]
    assert a == b


def test_messy_key_does_not_create_new_customer(con):
    assert con.execute("SELECT count(*) FROM hub_customer WHERE customer_number LIKE 'C001%'").fetchone()[0] == 1


def test_billing_only_customer_gets_a_hub_row(con):
    assert con.execute("SELECT count(*) FROM hub_customer WHERE customer_number = 'C005'").fetchone()[0] == 1


def test_unchanged_rows_add_no_satellite_history(con):
    hist = con.sql("""SELECT h.customer_number, count(*) FROM sat_customer_crm s
                      JOIN hub_customer h USING (hk_customer) GROUP BY 1""").fetchall()
    assert dict(hist) == {"C001": 1, "C002": 2, "C003": 2, "C004": 1}


def test_replaying_any_day_inserts_nothing(con):
    before = counts(con)
    for d in DAYS:
        inserted = load_day(con, d, crm(d), billing(d))
        assert set(inserted.values()) == {0}, d
    assert counts(con) == before


def test_out_of_order_replay_of_old_day(con):
    # Re-sending day 1 after day 3 must not re-add Mei's old email as a new version
    load_day(con, DAYS[0], crm(DAYS[0]), billing(DAYS[0]))
    rows = con.execute("""SELECT count(*) FROM sat_customer_crm s JOIN hub_customer h USING (hk_customer)
                      WHERE customer_number = 'C003'""").fetchone()[0]
    assert rows == 2


def test_asof_view_reflects_history(con):
    build_pit(con, DAYS)
    create_views(con)
    q = "SELECT state FROM customer_accounts_asof WHERE customer_number='C002' AND snapshot_date=?"
    assert con.execute(q, [DAYS[0]]).fetchone()[0] == "NJ"
    assert con.execute(q, [DAYS[1]]).fetchone()[0] == "PA"
    row = con.execute("""SELECT accounts, monthly_revenue FROM customer_accounts_asof
                     WHERE customer_number='C004' AND snapshot_date='2025-03-03'""").fetchone()
    assert row == (2, 135.0)


def test_customer_known_only_to_billing_is_flagged(con):
    build_pit(con, DAYS)
    create_views(con)
    flagged = con.sql("SELECT customer_number FROM customer_accounts_asof WHERE missing_crm_profile").fetchall()
    assert flagged == [("C005",)]
