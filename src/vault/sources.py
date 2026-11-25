"""Two operational systems that both know about customers, over three days of changes.

crm      customer profile: name, email, state   (key: customer_number)
billing  accounts and plans per customer        (keys: account_id, customer_number)
"""
from __future__ import annotations

import pandas as pd

CRM = {
    "2025-03-01": [("C001", "Ana Ruiz", "ana@mail.com", "PA"), ("C002", "Raj Patel", "raj@mail.com", "NJ"),
                   ("C003", "Mei Chen", "mei@mail.com", "NY")],
    # Raj moves to PA; Ana's row is re-sent unchanged (full extract); a new customer
    "2025-03-02": [("C001", "Ana Ruiz", "ana@mail.com", "PA"), ("C002", "Raj Patel", "raj@mail.com", "PA"),
                   ("C003", "Mei Chen", "mei@mail.com", "NY"), ("C004", "Omar Ali", "omar@mail.com", "DE")],
    # Mei changes email; trailing spaces / case differences in a key must not create a new customer
    "2025-03-03": [("c001 ", "Ana Ruiz", "ana@mail.com", "PA"), ("C003", "Mei Chen", "mei.chen@mail.com", "NY")],
}
BILLING = {
    "2025-03-01": [("A10", "C001", "Basic", 40.0), ("A20", "C002", "Unlimited", 65.0)],
    "2025-03-02": [("A10", "C001", "Unlimited", 65.0), ("A20", "C002", "Unlimited", 65.0), ("A30", "C003", "Basic", 40.0)],
    # Omar opens two accounts; billing knows a customer CRM has never sent (C005)
    "2025-03-03": [("A40", "C004", "Premium", 95.0), ("A41", "C004", "Basic", 40.0), ("A50", "C005", "Basic", 40.0)],
}


def crm(day: str) -> pd.DataFrame:
    return pd.DataFrame(CRM[day], columns=["customer_number", "name", "email", "state"])


def billing(day: str) -> pd.DataFrame:
    return pd.DataFrame(BILLING[day], columns=["account_id", "customer_number", "plan", "monthly_price"])
