import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import sqlite3
import requests
from bs4 import BeautifulSoup
import re

# 1. Configuration
TOKEN = "8609572351:AAG4MOToTMpQyqldyjOpFrWZVm_Re2U2tVo"
bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('tracker.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  product_name TEXT, 
                  current_price TEXT, 
                  url TEXT)''')
    conn.close()

# --- Command Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(KeyboardButton("🔍 Track Price"), KeyboardButton("📊 My History"))
    bot.send_message(message.chat.id, "👋 **PricePulse Pro Online**\n\nUse the buttons below to manage your tracking:", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def stop(message):
    bot.send_message(message.chat.id, "🛑 Session Ended.", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "🔍 Track Price")
def ask_for_link(message):
    bot.send_message(message.chat.id, "🔗 Paste the Amazon URL below:")

# --- 📊 HISTORY HANDLER (With Delete Buttons) ---

@bot.message_handler(commands=['list', 'history'])
@bot.message_handler(func=lambda message: message.text == "📊 My History")
def show_history(message):
    user_id = message.chat.id
    conn = sqlite3.connect('tracker.db')
    cursor = conn.cursor()
    # We fetch the ID now so we can delete specific items
    cursor.execute("SELECT id, product_name, current_price FROM products WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    products = cursor.fetchall()
    conn.close()

    if not products:
        bot.send_message(user_id, "📭 Your list is empty!")
        return

    bot.send_message(user_id, "📋 **Your Tracked Items:**", parse_mode='Markdown')

    for p_id, name, price in products:
        markup = InlineKeyboardMarkup()
        # Create a "Delete" button that sends the item ID to our backend
        delete_btn = InlineKeyboardButton("🗑️ Remove from List", callback_data=f"delete_{p_id}")
        markup.add(delete_btn)
        
        bot.send_message(user_id, f"🔹 **{name[:40]}...**\n💰 Price: ₹{price}", reply_markup=markup, parse_mode='Markdown')

# --- 🗑️ DELETE CALLBACK HANDLER ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_item(call):
    product_id = call.data.split("_")[1]
    
    conn = sqlite3.connect('tracker.db')
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    # Update the message to show it was deleted
    bot.edit_message_text(chat_id=call.message.chat.id, 
                         message_id=call.message.message_id, 
                         text="✅ **Item Removed Successfully!**", 
                         parse_mode='Markdown')
    # Optional: Alert the user with a small popup
    bot.answer_callback_query(call.id, "Product Deleted")

# --- 📦 AMAZON SCRAPER ---

@bot.message_handler(func=lambda message: "amazon.in" in message.text or "amzn.to" in message.text)
def handle_amazon_link(message):
    user_id = message.chat.id
    url_match = re.search(r'(https?://[^\s]+)', message.text)
    if not url_match: return
    
    url = url_match.group(1)
    print(f"📦 Link Received: {url[:50]}...") 
    bot.send_message(user_id, "🔍 Fetching price...")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.select_one('#productTitle')
        price = soup.select_one('.a-price-whole') or soup.select_one('#priceblock_ourprice')
        
        if title and price:
            p_name = title.get_text().strip()
            p_price = "".join(filter(str.isdigit, price.get_text()))
            
            conn = sqlite3.connect('tracker.db')
            conn.execute("INSERT INTO products (user_id, product_name, current_price, url) VALUES (?, ?, ?, ?)", (user_id, p_name, p_price, url))
            conn.commit()
            conn.close()
            bot.send_message(user_id, f"✅ **Tracked!**\n{p_name[:40]}...\nPrice: ₹{p_price}", parse_mode='Markdown')
        else:
            bot.send_message(user_id, "❌ Could not find details.")
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Error: {e}")

if __name__ == "__main__":
    init_db()
    print("🚀 PricePulse is ONLINE...")
    bot.polling(none_stop=True)