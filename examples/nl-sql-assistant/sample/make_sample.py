"""Build the sample shop database (SQLite): products, customers (with personal columns), sales.

    python3 make_sample.py [path]     # default: shop.db next to this file

Deterministic (fixed seed), fictional people, 555 phone numbers and .test email domains.
"""
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Ava", "Liam", "Priya", "Noah", "Mei", "Arjun", "Sofia", "Diego", "Aisha", "Ethan", "Kavya", "Omar",
         "Grace", "Ravi", "Hana", "Lucas", "Zara", "Mateo", "Nila", "Owen"]
LAST = ["Patel", "Nguyen", "Garcia", "Smith", "Kumar", "Chen", "Johnson", "Rao", "Lopez", "Brown"]
CITIES = ["Frisco", "Plano", "Dallas", "Austin", "Houston", "McKinney", "Irving", "Denton"]
PRODUCTS = [("Widget", "Hardware", 19.99), ("Gadget", "Hardware", 34.50), ("Sprocket", "Hardware", 7.25),
            ("Gizmo Pro", "Electronics", 129.00), ("Gizmo Mini", "Electronics", 59.00), ("Cable 2m", "Electronics", 9.99),
            ("Desk Lamp", "Home", 42.00), ("Mug", "Home", 12.00), ("Throw Pillow", "Home", 24.00),
            ("Notebook", "Office", 5.50), ("Pen Pack", "Office", 8.75), ("Stapler", "Office", 15.00),
            ("Yoga Mat", "Fitness", 29.00), ("Dumbbell 5kg", "Fitness", 39.00), ("Water Bottle", "Fitness", 18.00),
            ("Coffee Beans", "Grocery", 16.50), ("Green Tea", "Grocery", 9.00), ("Granola", "Grocery", 6.75),
            ("Backpack", "Travel", 64.00), ("Luggage Tag", "Travel", 4.99)]


def build(path):
    path = Path(path)
    if path.exists():
        path.unlink()
    rnd = random.Random(42)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE products (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, category TEXT NOT NULL, unit_price REAL NOT NULL);
        CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, city TEXT, signup_date TEXT);
        CREATE TABLE sales (sale_id INTEGER PRIMARY KEY, sale_date TEXT NOT NULL, customer_id INTEGER REFERENCES customers,
                            product_id INTEGER REFERENCES products, quantity INTEGER NOT NULL, amount REAL NOT NULL);
    """)
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", [(i + 1, *p) for i, p in enumerate(PRODUCTS)])
    start = date(2026, 1, 1)
    customers = []
    for i in range(1, 61):
        f, l = rnd.choice(FIRST), rnd.choice(LAST)
        customers.append((i, f"{f} {l}", f"{f.lower()}.{l.lower()}{i}@mail.test", f"214-555-{i:04d}",
                          rnd.choice(CITIES), (start + timedelta(days=rnd.randint(0, 200))).isoformat()))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)
    weights = [rnd.random() ** 2 for _ in PRODUCTS]
    sales = []
    for i in range(1, 801):
        pid = rnd.choices(range(1, len(PRODUCTS) + 1), weights)[0]
        qty = rnd.randint(1, 5)
        sales.append((i, (start + timedelta(days=rnd.randint(0, 300))).isoformat(), rnd.randint(1, 60), pid, qty,
                      round(qty * PRODUCTS[pid - 1][2], 2)))
    con.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?)", sales)
    con.commit()
    con.close()
    return path


if __name__ == "__main__":
    p = build(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("shop.db"))
    print(f"wrote {p}")
