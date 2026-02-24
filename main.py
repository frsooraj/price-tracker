import os
import requests
import mysql.connector
from bs4 import BeautifulSoup
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from flask import Flask

# --- 1. FLASK KEEP-ALIVE SERVER ---
# This server satisfies Render's requirement for an open HTTP port.
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    # Render provides the port via an environment variable
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Starts the Flask server in a separate background thread."""
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- 2. DATABASE CONFIGURATION ---
# Using hardcoded defaults as backup, but prioritizing Environment Variables
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
        use_pure=True
    )

# --- 3. SCRAPER ENGINE ---
def scrape_amazon_price(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en-GB,en-US;q=0.9,en;q=0.8"
    }
    try:
        # Sanitize URL
        clean_url = url.split('?')[0].split('ref')[0]
        response = requests.get(clean_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find Title
        title_tag = soup.find("span", {"id": "productTitle"})
        title = title_tag.get_text().strip()[:40] if title_tag else "Amazon Product"
        
        # Find Price
        price = None
        selectors = [("span", {"class": "a-price-whole"}), ("span", {"class": "a-offscreen"})]
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

# --- 4. TELEGRAM COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 PricePulse Bot is Live!\nCommands:\n/track [URL] - Start monitoring\n/list - View your items")

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Please provide a link. Usage: /track [URL]")
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
            await msg.edit_text(f"✅ Now Tracking:\n📦 {title}\n💰 Price: ₹{price:,.2f}")
        except Exception as e:
            await msg.edit_text(f"❌ Database Error: {e}")
    else:
        await msg.edit_text("❌ Error: Could not extract price. Ensure it's a valid Amazon India link.")

async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT product_name, current_price FROM products WHERE telegram_id = %s", (update.effective_user.id,))
        rows = cursor.fetchall()
        
        if not rows:
            await update.message.reply_text("Your watchlist is empty.")
        else:
            text = "📋 **Your Watchlist:**\n\n"
            for r in rows:
                text += f"🔹 {r[0]} - **₹{r[1]:,.2f}**\n"
            await update.message.reply_text(text, parse_mode='Markdown')
        cursor.close()
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ DB Error: {e}")

# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    # A. Start the Flask server in a separate thread first
    keep_alive()
    print("🌐 Keep-alive server running on port 10000...")

    # B. Initialize Database Table
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
        print("✅ Database connection established.")
    except Exception as e:
        print(f"❌ DB Setup Failed: {e}")

    # C. Start the Telegram Bot (This is a blocking call)
    TOKEN = os.getenv("TELEGRAM_TOKEN", "8543572699:AAEQkrW8GfVcDJhIpdwMKU2KussdhwC0SJA")
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("list", list_items))
    
    print("🤖 Bot is starting polling...")
    # This line "blocks" the script, which is why Flask must be in a thread above it
    application.run_polling()