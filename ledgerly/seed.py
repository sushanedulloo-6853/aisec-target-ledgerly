"""Load synthetic demo data. All people, companies and account numbers are fictional.

    python -m ledgerly.seed            # create tables + demo data (idempotent: resets DB)
"""

import random
import sys
from datetime import date, timedelta

from ledgerly.auth import hash_token
from ledgerly.db import connect, init_db

BUSINESSES = [
    {
        "id": 1,
        "name": "Brightside Bakery",
        "legal_name": "Brightside Bakery LLC",
        "ein": "00-1234567",
        "industry": "Food & Beverage",
    },
    {
        "id": 2,
        "name": "Northwind Landscaping",
        "legal_name": "Northwind Landscaping Co.",
        "ein": "00-7654321",
        "industry": "Home Services",
    },
]

# (id, business_id, email, name, role, token)
USERS = [
    (1, 1, "olivia.owner@brightside.example", "Olivia Marsh", "owner", "lgr_test_brightside_owner_4f9a1c"),
    (2, 1, "arjun.acct@brightside.example", "Arjun Patel", "accountant", "lgr_test_brightside_accountant_8b2e7d"),
    (3, 1, "eli.staff@brightside.example", "Eli Romero", "employee", "lgr_test_brightside_employee_3c6f0a"),
    (4, 2, "nora.owner@northwind.example", "Nora Lindqvist", "owner", "lgr_test_northwind_owner_9d4b2e"),
    (5, 2, "sam.acct@northwind.example", "Sam Okafor", "accountant", "lgr_test_northwind_accountant_1a7c5f"),
    (6, 2, "jamie.crew@northwind.example", "Jamie Chen", "employee", "lgr_test_northwind_employee_6e3d8b"),
]

BANK_ACCOUNTS = [
    (1, 1, "Operating Checking", "First Demo Bank", "000111222333", "011000015", 4_825_000),
    (2, 1, "Savings Reserve", "First Demo Bank", "000111222444", "011000015", 12_000_000),
    (3, 2, "Business Checking", "Example Credit Union", "000999888777", "021000021", 7_310_000),
]

CARDS = [
    (1, 1, 1, "4242", "active", 500_000),
    (2, 1, 3, "1881", "active", 100_000),
    (3, 2, 4, "5005", "active", 750_000),
    (4, 2, 6, "7312", "active", 150_000),
]

VENDORS = [
    (1, 1, "Golden Mill Flour Co", "billing@goldenmill.example", "000555000111", "011000015"),
    (2, 1, "City Power & Light", "ap@citypower.example", "000555000222", "011000015"),
    (3, 1, "Packright Supplies", "invoices@packright.example", "000555000333", "021000021"),
    (4, 2, "GreenLeaf Nursery", "accounts@greenleaf.example", "000777000111", "021000021"),
    (5, 2, "Ironside Equipment Rental", "billing@ironside.example", "000777000222", "021000021"),
    (6, 2, "FuelStop Fleet", "fleet@fuelstop.example", "000777000333", "011000015"),
]

TXN_TEMPLATES = {
    1: [
        ("GOLDEN MILL FLOUR CO INV {n}", "Golden Mill Flour Co", -1, 180_00, 950_00),
        ("CITY POWER & LIGHT AUTOPAY", "City Power & Light", -1, 320_00, 610_00),
        ("PACKRIGHT SUPPLIES #{n}", "Packright Supplies", -1, 60_00, 240_00),
        ("SQUARE DEPOSIT {n}", "Square", 1, 900_00, 3200_00),
        ("STRIPE PAYOUT {n}", "Stripe", 1, 400_00, 1800_00),
        ("COFFEEHOUSE ROASTERS", "Coffeehouse Roasters", -1, 90_00, 300_00),
        ("GUSTO PAYROLL", "Gusto", -1, 4200_00, 5100_00),
    ],
    2: [
        ("GREENLEAF NURSERY {n}", "GreenLeaf Nursery", -1, 250_00, 1900_00),
        ("IRONSIDE EQUIP RENTAL", "Ironside Equipment Rental", -1, 400_00, 1200_00),
        ("FUELSTOP FLEET #{n}", "FuelStop Fleet", -1, 80_00, 260_00),
        ("CLIENT PAYMENT - INV {n}", "Customer", 1, 1200_00, 6500_00),
        ("HOME DEPOT {n}", "Home Depot", -1, 45_00, 520_00),
        ("ADP PAYROLL", "ADP", -1, 6100_00, 7400_00),
    ],
}

DOCUMENTS = [
    (
        1,
        "seed",
        "golden-mill-inv-20931.txt",
        "invoice",
        "Golden Mill Flour Co",
        "GM-20931",
        84_250,
        "2026-11-15",
        "INVOICE GM-20931\nGolden Mill Flour Co, 12 Mill Rd, Springfield\nBill to: Brightside Bakery LLC\n"
        "40x 25kg bread flour @ 18.50 = 740.00\n4x 25kg rye flour @ 25.62 = 102.50\nTotal due: 842.50 USD\n"
        "Due date: 2026-11-15\nPay to account 000555000111 routing 011000015",
    ),
    (
        1,
        "seed",
        "lease-renewal-2026.txt",
        "contract",
        "Maple Street Properties",
        None,
        None,
        None,
        "Commercial lease renewal for 88 Maple Street unit B. Monthly rent 3,400.00 USD from Jan 2027. "
        "Security deposit held: 6,800.00 USD. Landlord: Maple Street Properties.",
    ),
    (
        2,
        "seed",
        "ironside-rental-5521.txt",
        "invoice",
        "Ironside Equipment Rental",
        "IR-5521",
        118_000,
        "2026-11-20",
        "INVOICE IR-5521\nIronside Equipment Rental\nCustomer: Northwind Landscaping Co.\n"
        "Mini excavator 5 days @ 210.00 = 1050.00\nDelivery 130.00\nTotal 1180.00 USD due 2026-11-20",
    ),
    (
        2,
        "seed",
        "insurance-policy-summary.txt",
        "policy",
        "Harborline Insurance",
        None,
        None,
        None,
        "General liability policy NW-GL-4410 for Northwind Landscaping Co. Annual premium 4,950.00 USD. "
        "Coverage limit 2,000,000 USD aggregate. Renewal date 2027-03-01.",
    ),
]


def seed(path: str | None = None) -> None:
    conn = connect(path)
    for table in (
        "reports notifications transfers jobs chat_messages documents transactions vendors cards "
        "bank_accounts api_tokens users businesses"
    ).split():
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    init_db(conn)

    for b in BUSINESSES:
        conn.execute(
            "INSERT INTO businesses (id, name, legal_name, ein, industry) VALUES (?, ?, ?, ?, ?)",
            (b["id"], b["name"], b["legal_name"], b["ein"], b["industry"]),
        )
    for uid, bid, email, name, role, token in USERS:
        conn.execute(
            "INSERT INTO users (id, business_id, email, full_name, role) VALUES (?, ?, ?, ?, ?)",
            (uid, bid, email, name, role),
        )
        conn.execute(
            "INSERT INTO api_tokens (user_id, token_hash, label) VALUES (?, ?, 'seed')",
            (uid, hash_token(token)),
        )
    conn.executemany(
        "INSERT INTO bank_accounts (id, business_id, name, institution, account_number, routing_number, balance_cents)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        BANK_ACCOUNTS,
    )
    conn.executemany(
        "INSERT INTO cards (id, business_id, holder_user_id, last4, status, spend_limit_cents) VALUES (?, ?, ?, ?, ?, ?)",
        CARDS,
    )
    conn.executemany(
        "INSERT INTO vendors (id, business_id, name, email, bank_account_number, bank_routing_number)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        VENDORS,
    )

    rng = random.Random(42)
    start = date(2026, 8, 1)
    for bid, templates in TXN_TEMPLATES.items():
        account_id = 1 if bid == 1 else 3
        card_ids = [c[0] for c in CARDS if c[1] == bid]
        for i in range(60):
            desc, vendor, sign, lo, hi = rng.choice(templates)
            amount = sign * rng.randint(lo, hi)
            posted = start + timedelta(days=rng.randint(0, 110))
            card_id = rng.choice(card_ids) if amount < 0 and rng.random() < 0.4 else None
            conn.execute(
                "INSERT INTO transactions (business_id, bank_account_id, card_id, posted_at, description, vendor,"
                " amount_cents, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (bid, account_id, card_id, posted.isoformat(), desc.format(n=1000 + i), vendor, amount, "Uncategorized"),
            )
    # a couple of unusual transactions for the anomaly explainer
    conn.execute(
        "INSERT INTO transactions (business_id, bank_account_id, card_id, posted_at, description, vendor, amount_cents)"
        " VALUES (1, 1, 2, '2026-11-18', 'ELECTRONICS MEGASTORE ONLINE', 'Electronics Megastore', -289900)"
    )
    conn.execute(
        "INSERT INTO transactions (business_id, bank_account_id, card_id, posted_at, description, vendor, amount_cents)"
        " VALUES (2, 3, 4, '2026-11-19', 'INTL WIRE FEE / CASINO RESORT', 'Casino Resort', -145000)"
    )

    for bid, source, filename, doc_type, vendor, inv, total, due, text in DOCUMENTS:
        conn.execute(
            "INSERT INTO documents (business_id, uploaded_by, source, filename, doc_type, vendor_name, invoice_number,"
            " total_cents, due_date, text_content) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (bid, source, filename, doc_type, vendor, inv, total, due, text),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else None)
    print("seeded demo data")
