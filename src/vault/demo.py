"""Load three days, replay them, and print what the vault and marts show."""
import duckdb

from vault.marts import build_pit, create_views
from vault.model import counts, load_day
from vault.sources import CRM, billing, crm


def main() -> None:
    con = duckdb.connect()
    days = list(CRM)
    print("== daily loads (rows inserted per table)")
    for d in days:
        print(d, load_day(con, d, crm(d), billing(d)))
    print("\n== replay every day again")
    for d in days:
        print(d, load_day(con, d, crm(d), billing(d)))
    print("\n== table sizes", counts(con))
    print("\n== CRM satellite history")
    print(con.sql("""SELECT h.customer_number, s.load_date, s.email, s.state
                     FROM sat_customer_crm s JOIN hub_customer h USING (hk_customer)
                     ORDER BY 1, 2""").df().to_string(index=False))
    build_pit(con, days)
    create_views(con)
    print("\n== customer_accounts_asof")
    print(con.sql("SELECT * FROM customer_accounts_asof ORDER BY snapshot_date, customer_number")
          .df().to_string(index=False))


if __name__ == "__main__":
    main()
