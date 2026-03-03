import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import threading
import time

# 1. Configuration
TOKEN = "8609572351:AAG4MOToTMpQyqldyjOpFrWZVm_Re2U2tVo"
bot = telebot.TeleBot(TOKEN)

# 2. Database Initialization
def init_db():
    conn = sqlite3.connect('tracker.db')
    # Main Products Table
    conn.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  product_name TEXT, 
                  current_price INTEGER, 
                  url TEXT)''')
    # History Logs Table
    conn.execute('''CREATE TABLE IF NOT EXISTS price_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  product_id INTEGER, 
                  price INTEGER, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(product_id) REFERENCES products(id))''')
    conn.close()

# --- 🕵️ Monitor Thread (Runs every 60 seconds) ---
def monitor_prices():
    while True:
        try:
            conn = sqlite3.connect('tracker.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, product_name, current_price, url FROM products")
            items = cursor.fetchall()
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
            
            for p_id, user_id, name, stored_price, url in items:
                res = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                price_tag = soup.select_one('.a-price-whole') or soup.select_one('#priceblock_ourprice')
                
                if price_tag:
                    live_price = int("".join(filter(str.isdigit, price_tag.get_text())))
                    
                    # Log every check into price_logs
                    cursor.execute("INSERT INTO price_logs (product_id, price) VALUES (?, ?)", (p_id, live_price))
                    
                    # Alert if price is lower than what we have stored
                    if live_price < int(stored_price):
                        msg = (f"🚨 **PRICE DROP!**\n\n{name[:40]}...\n"
                               f"📉 Was: ₹{stored_price}\n🔥 **Now: ₹{live_price}**\n\n[Link]({url})")
                        bot.send_message(user_id, msg, parse_mode='Markdown')
                        cursor.execute("UPDATE products SET current_price = ? WHERE id = ?", (live_price, p_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Monitor Error: {e}")
        time.sleep(60)

threading.Thread(target=monitor_prices, daemon=True).start()

# --- BOT COMMANDS ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(KeyboardButton("🔍 Track Price"), KeyboardButton("📊 My History"))
    bot.send_message(message.chat.id, "🤖 **PricePulse Pro v2.0**\nTracking and History are active!", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def stop(message):
    bot.send_message(message.chat.id, "🛑 Session Closed.", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "🔍 Track Price" or m.text == "/track")
def ask_link(message):
    bot.send_message(message.chat.id, "🔗 Paste your Amazon India link below:")

@bot.message_handler(func=lambda m: m.text == "📊 My History" or m.text == "/history" or m.text == "/list")
def show_list(message):
    user_id = message.chat.id
    conn = sqlite3.connect('tracker.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, product_name, current_price, url FROM products WHERE user_id = ?", (user_id,))
    data = cursor.fetchall()
    
    if not data:
        bot.send_message(user_id, "📭 Your list is empty!")
        return

    for p_id, name, price, url in data:
        # Get lowest price ever recorded for this item
        cursor.execute("SELECT MIN(price) FROM price_logs WHERE product_id = ?", (p_id,))
        lowest = cursor.fetchone()[0]
        
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🗑️ Remove", callback_data=f"del_{p_id}"))
        bot.send_message(user_id, f"🔹 **{name[:35]}...**\n💰 Current: ₹{price}\n📉 Lowest: ₹{lowest}\n[Link]({url})", 
                         reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_item(call):
    p_id = call.data.split("_")[1]
    conn = sqlite3.connect('tracker.db')
    conn.execute("DELETE FROM price_logs WHERE product_id = ?", (p_id,))
    conn.execute("DELETE FROM products WHERE id = ?", (p_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text("✅ Item and history removed.", call.message.chat.id, call.message.message_id)

# --- THE LINK HANDLER (Amazon Link Scraper) ---

@bot.message_handler(func=lambda m: "amazon.in" in m.text or "amzn.to" in m.text)
def handle_link(message):
    user_id = message.chat.id
    url = re.search(r'(https?://[^\s]+)', message.text).group(1)
    bot.send_message(user_id, "🔍 Checking Amazon...")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        title = soup.select_one('#productTitle').get_text().strip()
        price_raw = soup.select_one('.a-price-whole') or soup.select_one('#priceblock_ourprice')
        price = int("".join(filter(str.isdigit, price_raw.get_text())))
        
        # Save to DB
        conn = sqlite3.connect('tracker.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (user_id, product_name, current_price, url) VALUES (?, ?, ?, ?)", 
                       (user_id, title, price, url))
        p_id = cursor.lastrowid
        # Log initial price
        cursor.execute("INSERT INTO price_logs (product_id, price) VALUES (?, ?)", (p_id, price))
        conn.commit()
        conn.close()
        
        bot.send_message(user_id, f"✅ **Tracked Successfully!**\n\n{title[:40]}...\nPrice: ₹{price}", parse_mode='Markdown')
    except Exception as e:
        print(f"Scrape Error: {e}")
        bot.send_message(user_id, "❌ Error. Amazon might be blocking me. Try again later.")

if __name__ == "__main__":
    init_db()
    print("🚀 Bot is LIVE with Price History Tracking...")
    bot.polling(none_stop=True)