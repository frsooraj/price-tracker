import sqlite3
from tabulate import tabulate

def show_table():
    conn = sqlite3.connect('tracker.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, u.first_name, u.username, p.product_name, p.current_price, p.target_price
        FROM products p
        LEFT JOIN users u ON p.user_id = u.user_id
    """)
    rows = cursor.fetchall()
    
    # Prepare data for tabulate
    table_data = []
    for row in rows:
        p_id, first_name, username, product_name, price, target = row
        first_name = first_name or "Unknown"
        username = f"@{username}" if username else "-"
        target_str = str(target) if target else "NULL"
        table_data.append([p_id, first_name, username, product_name, f"₹{price}", target_str])
    
    # Headers
    headers = ["ID", "NAME", "@USERNAME", "PRODUCT NAME", "PRICE", "TARGET"]
    
    # Print the table
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"\nTotal: {len(rows)} products")
    conn.close()

if __name__ == '__main__':
    show_table()