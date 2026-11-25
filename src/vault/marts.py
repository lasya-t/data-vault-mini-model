"""Business-facing layer on top of the raw vault: a PIT table and information mart views."""
from __future__ import annotations


def build_pit(con, snapshot_dates: list[str]) -> None:
    """Point-in-time table: for each customer and snapshot date, which satellite row was current.

    Queries then join on exact keys instead of each repeating 'latest row on or before date' logic.
    """
    dates = ", ".join(f"(DATE '{d}')" for d in snapshot_dates)
    con.execute(f"""
        CREATE OR REPLACE TABLE pit_customer AS
        SELECT h.hk_customer, d.snapshot_date,
               (SELECT max(s.load_date) FROM sat_customer_crm s
                WHERE s.hk_customer = h.hk_customer AND s.load_date <= d.snapshot_date) AS crm_load_date
        FROM hub_customer h CROSS JOIN (VALUES {dates}) AS d(snapshot_date)
        WHERE h.load_date <= d.snapshot_date
    """)


def create_views(con) -> None:
    con.execute("""
        CREATE OR REPLACE VIEW customer_accounts_asof AS
        -- one row per customer per snapshot: profile as of that date, plus active accounts and plans
        WITH acct AS (
            SELECT l.hk_customer, d.snapshot_date, count(*) AS accounts, sum(s.monthly_price) AS monthly_revenue
            FROM link_customer_account l
            JOIN (SELECT DISTINCT snapshot_date FROM pit_customer) d ON l.load_date <= d.snapshot_date
            JOIN sat_account_billing s ON s.hk_account = l.hk_account
             AND s.load_date = (SELECT max(load_date) FROM sat_account_billing x
                                WHERE x.hk_account = s.hk_account AND x.load_date <= d.snapshot_date)
            GROUP BY ALL
        )
        SELECT p.snapshot_date, h.customer_number, c.name, c.email, c.state,
               coalesce(a.accounts, 0) AS accounts, coalesce(a.monthly_revenue, 0) AS monthly_revenue,
               c.hk_customer IS NULL AS missing_crm_profile
        FROM pit_customer p
        JOIN hub_customer h USING (hk_customer)
        LEFT JOIN sat_customer_crm c ON c.hk_customer = p.hk_customer AND c.load_date = p.crm_load_date
        LEFT JOIN acct a ON a.hk_customer = p.hk_customer AND a.snapshot_date = p.snapshot_date
    """)
