import sqlite3

def init_db():
    conn = sqlite3.connect('tracker.db')
    cursor = conn.cursor()
    # Table for Users (Module 2)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            telegram_id INTEGER PRIMARY KEY, 
            username TEXT
        )''')
    # Table for Products (Module 2)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            product_name TEXT,
            url TEXT,
            current_price REAL,
            FOREIGN KEY (telegram_id) REFERENCES Users(telegram_id)
        )''')
    conn.commit()
    conn.close()