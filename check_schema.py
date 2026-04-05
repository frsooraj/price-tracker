import sqlite3
conn = sqlite3.connect('tracker.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT p.id, u.first_name, u.username, p.product_name, p.current_price, p.target_price
    FROM products p
    LEFT JOIN users u ON p.user_id = u.user_id
    ORDER BY p.id
""")
rows = cursor.fetchall()

for row in rows:
    pid, fname, uname, pname, price, target = row
    fname = fname or "?"
    uname = ("@"+uname) if uname else ""
    pname = pname[:35]
    tgt = str(target) if target else "-"
    print(f"{pid}: {fname} {uname}")
    print(f"   {pname}...")
    print(f"   Rs.{price} | Target: {tgt}")
    print()

print(f"Total: {len(rows)} products")
conn.close()
