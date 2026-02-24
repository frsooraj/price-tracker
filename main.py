import os
import requests
import mysql.connector
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# --- 1. FREE TIER KEEP-ALIVE (FLASK) ---
# Render's free 'Web Service' tier needs an open port.
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    # Render uses port 10000 by default, but we'll use 8080 or let Render decide
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. CONFIGURATION & DATABASE ---
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_TOKEN", "8543572699:AAEQkrW8GfVcDJhIpdwMKU2KussdhwC0SJA")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "mysql-26e2de24-sheenaanil1977-8be8.l.aivencloud.com"),
    "user": os.getenv("DB_USER", "avnadmin"),
    "password": os.getenv("DB_PASSWORD", "AVNS_bsHqrqk5TfZUxCIrPIC"),
    "database": os.getenv("DB_NAME", "defaultdb"),
    "port": int(os.getenv("DB_PORT", 14351))
}

def get_db_connection():
    return mysql.connector.connect(
        **DB_CONFIG,
        use_pure=True,  # Fixes Windows 'Named Pipe' errors
        ssl_disabled=False 
    )

# --- 3. SCRAPER ENGINE ---
def scrape_amazon_price(url):
    # Clean URL: Remove everything after the '?'
    clean_url = url.split('?')[0].split('ref')[0]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en-GB,en-US;q=0.9,en;q=0.8"
    }
    try:
        response = requests.get(clean_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Extract Title
        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text().strip()[:40] + "..." if title_tag else "Amazon Product"
        
        # Extract Price (Checking multiple possible Amazon tags)
        price = None
        selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"class": "a-offscreen"}),
            ("span", {"id": "priceblock_ourprice"})
        ]
        
        for tag, attrs in selectors:
            el = soup.find(tag, attrs)
            if el:
                p_str = el.get_text().replace('₹', '').replace(',', '').strip()
                try:
                    price = float(p_str)
                    break
                except: continue
        
        return title, price
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None, None

# --- 4. BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 PricePulse Active!\nUse /track [URL] to monitor prices.")

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /track [Amazon URL]")
        return

    url = context.args[0]
    msg = await update.message.reply_text("🔍 Fetching price...")
    
    title, price = scrape_amazon_price(url)
    
    if price:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO products (telegram_id, product_name, current_price, url) VALUES (%s, %s, %s, %s)",
                (update.effective_user.id, title, price, url)
            )
            conn.commit()
            cursor.close()
            conn.close()
            await msg.edit_text(f"✅ Tracking Started!\n📦 {title}\n💰 Price: ₹{price:,.2f}")
        except Exception as e:
            await msg.edit_text(f"❌ DB Error: {e}")
    else:
        await msg.edit_text("❌ Could not fetch price. Try a shorter link.")

async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, product_name, current_price FROM products WHERE telegram_id = %s", (update.effective_user.id,))
        rows = cursor.fetchall()
        
        if not rows:
            await update.message.reply_text("Watchlist is empty.")
        else:
            text = "📋 **Watchlist:**\n\n"
            for r in rows:
                text += f"🔹 {r[1]} - **₹{r[2]:,.2f}**\n"
            await update.message.reply_text(text, parse_mode='Markdown')
        cursor.close()
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    # Start the keep-alive server
    keep_alive()
    print("🌐 Keep-alive server started.")

    # DB Table Initialization
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                telegram_id BIGINT,
                product_name VARCHAR(255),
                current_price FLOAT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database ready.")
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")

    # Start Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("list", list_items))
    
    print("🤖 Bot is live...")
    app.run_polling()