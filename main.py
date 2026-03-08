import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import threading
import time
import random
import os
from flask import Flask

# --- 1. FLASK KEEP-ALIVE SERVER ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "PricePulse Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

# --- 2. Configuration ---
TOKEN = "8609572351:AAG4MOToTMpQyqldyjOpFrWZVm_Re2U2tVo"
bot = telebot.TeleBot(TOKEN)

# FIX: global lock to prevent simultaneous DB access across threads
db_lock = threading.Lock()

# --- FIX: single function to get DB connection with timeout ---
def get_conn():
    conn = sqlite3.connect('tracker.db', timeout=20, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")  # WAL mode allows concurrent reads
    return conn

# --- Scraper headers ---
def get_headers():
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    return {
        "User-Agent": random.choice(agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }

# --- Clean Amazon URL ---
def clean_amazon_url(url):
    asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    if asin_match:
        asin = asin_match.group(1)
        return f"https://www.amazon.in/dp/{asin}"
    return url

# --- Scraper core ---
def scrape_amazon(url):
    clean_url = clean_amazon_url(url)
    session = requests.Session()
    session.headers.update(get_headers())
    res = session.get(clean_url, timeout=15, allow_redirects=True)

    if res.status_code != 200:
        return None, None, f"HTTP {res.status_code}"

    soup = BeautifulSoup(res.text, 'html.parser')

    title_tag = soup.select_one('#productTitle')
    if not title_tag:
        return None, None, "Title not found - Amazon may be blocking the request"
    title = title_tag.get_text().strip()

    price_selectors = [
        '.a-price .a-offscreen', '#priceblock_ourprice', '#priceblock_dealprice',
        '#priceblock_saleprice', '.priceToPay .a-offscreen', '.apexPriceToPay .a-offscreen',
        '#corePrice_feature_div .a-offscreen', '#corePriceDisplay_desktop_feature_div .a-offscreen',
        '.a-price[data-a-color="price"] .a-offscreen', '#price_inside_buybox', '#newBuyBoxPrice',
        '.reinventPricePriceToPayMargin .a-offscreen',
    ]

    price = None
    for selector in price_selectors:
        tag = soup.select_one(selector)
        if tag:
            text = tag.get_text().strip().replace(',', '').replace('₹', '').replace(' ', '')
            digits = "".join(filter(str.isdigit, text.split('.')[0]))
            if digits:
                price = int(digits)
                break

    if not price:
        return title, None, "Price not found - item may be out of stock or unavailable"
    return title, price, None

# --- Database Initialization ---
def init_db():
    with db_lock:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                      product_name TEXT, current_price INTEGER, url TEXT,
                      target_price INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS price_logs 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, 
                      price INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(product_id) REFERENCES products(id))''')
        conn.commit()
        conn.close()

# --- Monitor Thread ---
def monitor_prices():
    while True:
        try:
            with db_lock:
                conn = get_conn()
                cursor = conn.cursor()
                cursor.execute("SELECT id, user_id, product_name, current_price, url, target_price FROM products")
                items = cursor.fetchall()
                conn.close()

            for p_id, user_id, name, stored_price, url, target in items:
                try:
                    _, live_price, err = scrape_amazon(url)
                    if err or not live_price:
                        continue

                    with db_lock:
                        conn = get_conn()
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO price_logs (product_id, price) VALUES (?, ?)", (p_id, live_price))

                        if live_price < int(stored_price):
                            bot.send_message(user_id, f"🚨 *DROP!*\n{name[:30]}..\n📉 ₹{stored_price} -> 🔥 ₹{live_price}", parse_mode='Markdown')
                            cursor.execute("UPDATE products SET current_price = ? WHERE id = ?", (live_price, p_id))

                        if target and live_price <= int(target):
                            bot.send_message(user_id, f"🎯 *Target Reached!*\n{name[:30]}..\n💰 Current: ₹{live_price}\n🎯 Target: ₹{target}", parse_mode='Markdown')

                        conn.commit()
                        conn.close()

                    time.sleep(3)
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(60)

# --- BOT COMMANDS ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(KeyboardButton("🔍 Track Price"), KeyboardButton("📊 My History"))
    bot.send_message(message.chat.id, "🤖 *PricePulse Pro v2.0*", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == "🔍 Track Price")
@bot.message_handler(commands=['track'])
def ask_link(message):
    bot.send_message(message.chat.id, "🔗 Paste your Amazon India link below:")

@bot.message_handler(func=lambda m: m.text in ["/list", "📊 My History"])
def show_list(message):
    user_id = message.chat.id
    with db_lock:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, product_name, current_price, url, target_price FROM products WHERE user_id = ?", (user_id,))
        data = cursor.fetchall()

        if not data:
            bot.send_message(user_id, "📭 No products tracked yet!")
            conn.close()
            return

        for p_id, name, price, url, target in data:
            cursor.execute("SELECT MIN(CAST(price AS INTEGER)) FROM price_logs WHERE product_id = ?", (p_id,))
            lowest = cursor.fetchone()[0] or price

            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🗑️ Remove", callback_data=f"del_{p_id}"))

            bot.send_message(
                user_id,
                f"🔹 *{name[:30]}..*\n💰 ₹{price}\n📉 Low: ₹{lowest}\n🎯 Target: {target if target else 'Not set'}\n🆔 ID: `{p_id}`",
                reply_markup=markup,
                parse_mode='Markdown'
            )
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_item(call):
    p_id = call.data.split("_")[1]
    with db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM price_logs WHERE product_id = ?", (p_id,))
        conn.execute("DELETE FROM products WHERE id = ?", (p_id,))
        conn.commit()
        conn.close()
    bot.answer_callback_query(call.id, "✅ Removed!")
    bot.edit_message_text("✅ Removed.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text and ("amazon.in" in m.text or "amzn.to" in m.text or m.text.startswith("http")))
def handle_link(message):
    user_id = message.chat.id
    try:
        url_match = re.search(r'(https?://[^\s]+)', message.text)
        if not url_match:
            bot.send_message(user_id, "⚠️ Could not find a valid URL. Please try again.")
            return
        url = url_match.group(1)
        clean_url = clean_amazon_url(url)

        # Check duplicate
        with db_lock:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT id, product_name, current_price FROM products WHERE user_id = ? AND url = ?", (user_id, clean_url))
            existing = cursor.fetchone()
            conn.close()

        if existing:
            p_id, name, price = existing
            bot.send_message(user_id, f"⚠️ *Already tracking this product!*\n{name[:40]}..\n💰 ₹{price}\n🆔 ID: `{p_id}`", parse_mode='Markdown')
            return

        wait_msg = bot.send_message(user_id, "📡 *Scraping Amazon... please wait*", parse_mode='Markdown')
        title, price, error = scrape_amazon(url)

        if error:
            bot.edit_message_text(f"❌ *Failed:* {error}", user_id, wait_msg.message_id, parse_mode='Markdown')
            return

        with db_lock:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO products (user_id, product_name, current_price, url, target_price) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, price, clean_url, None)
            )
            p_id = cursor.lastrowid
            cursor.execute("INSERT INTO price_logs (product_id, price) VALUES (?, ?)", (p_id, price))
            conn.commit()
            conn.close()

        bot.edit_message_text(
            f"✅ *Added!*\n{title[:40]}..\n💰 ₹{price}\n🎯 Target: Not set\n\nUse /setprice {p_id} <amount> to set a target.",
            user_id, wait_msg.message_id, parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(user_id, "⚠️ *System Error.* Check link and try again.")

@bot.message_handler(commands=['setprice'])
def set_price(message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.send_message(message.chat.id, "⚠️ Usage: /setprice <product_id> <target_price>")
            return
        p_id = int(parts[1])
        target = int(parts[2])

        with db_lock:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE products SET target_price = ? WHERE id = ? AND user_id = ?", (target, p_id, message.chat.id))
            affected = cursor.rowcount
            conn.commit()
            conn.close()

        if affected == 0:
            bot.send_message(message.chat.id, "⚠️ Product not found or does not belong to you.")
        else:
            bot.send_message(message.chat.id, f"✅ Target price set for product {p_id}: ₹{target}")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Invalid input. Must be numbers.")
    except Exception as e:
        print(f"Error in set_price: {e}")
        bot.send_message(message.chat.id, "⚠️ Something went wrong. Please try again.")

# --- Entry Point ---
if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    print("🌐 Keep-alive server running...")
    threading.Thread(target=monitor_prices, daemon=True).start()
    print("📉 Price monitor active...")
    print("🤖 Bot is running...")
    bot.infinity_polling()