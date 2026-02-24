import os
import requests
import mysql.connector
from bs4 import BeautifulSoup
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# 1. SMART LOAD CONFIGURATION
# This ensures Python finds the .env file in the same folder as the script
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_HOST = os.getenv("DB_HOST")

# Security Check: Alert if .env variables are missing
if not TOKEN or not DB_HOST:
    print("⚠️  WARNING: .env variables not found!")
    print(f"Check if this file exists and is not empty: {env_path}")
    print("Attempting to run with fallback/hardcoded values for testing...")

# 2. DATABASE CONFIGURATION
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "mysql-26e2de24-sheenaanil1977-8be8.l.aivencloud.com"),
    "user": os.getenv("DB_USER", "avnadmin"),
    "password": os.getenv("DB_PASSWORD", "AVNS_bsHqrqk5TfZUxCIrPIC"),
    "database": os.getenv("DB_NAME", "defaultdb"),
    "port": int(os.getenv("DB_PORT", 14351))
}

def get_db_connection():
    # 'use_pure=True' prevents the "Named Pipe" error on Windows
    return mysql.connector.connect(
        **DB_CONFIG,
        use_pure=True,
        ssl_disabled=False 
    )

# 3. AMAZON SCRAPER ENGINE
def scrape_amazon_price(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # 1. Get Title
        title = "Amazon Product"
        title_tag = soup.find("span", {"id": "productTitle"})
        if title_tag:
            title = title_tag.get_text().strip()[:40] + "..."

        # 2. Try 4 different price locations
        price_selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"id": "priceblock_ourprice"}),
            ("span", {"id": "priceblock_dealprice"}),
            ("span", {"class": "a-offscreen"})
        ]

        for tag, attrs in price_selectors:
            price_element = soup.find(tag, attrs)
            if price_element:
                raw_price = price_element.get_text().replace('₹', '').replace(',', '').strip()
                # If there's a decimal (like 999.00), take the part before the dot
                clean_price = raw_price.split('.')[0]
                if clean_price.isdigit():
                    return title, float(clean_price)

        return title, None
    except Exception as e:
        print(f"Scraper error: {e}")
        return None, None

# 4. BOT COMMAND HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 PricePulse Active! Send /track [URL] to monitor an Amazon product.")

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /track [Amazon URL]")
        return

    raw_url = context.args[0]
    
    # --- URL CLEANER LOGIC ---
    # This takes a long link and cuts it at the '?' or 'ref'
    clean_url = raw_url.split('?')[0].split('ref')[0]
    # -------------------------

    wait_msg = await update.message.reply_text("🔍 Cleaning link and fetching price...")
    
    # Use the clean_url for scraping
    title, price = scrape_amazon_price(clean_url)
    
    if price:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Store the CLEAN url in the database
            query = "INSERT INTO products (telegram_id, product_name, current_price, url) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (update.effective_user.id, title, price, clean_url))
            conn.commit()
            cursor.close()
            conn.close()
            await wait_msg.edit_text(f"✅ Tracking Started!\n📦 {title}\n💰 Current Price: ₹{price:,.2f}")
        except Exception as e:
            await wait_msg.edit_text(f"❌ Database Error: {e}")
    else:
        await wait_msg.edit_text("❌ Amazon is blocking this specific link format. Try a different product or shorten the link.")

async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, product_name, current_price FROM products WHERE telegram_id = %s", (update.effective_user.id,))
        rows = cursor.fetchall()
        
        if not rows:
            await update.message.reply_text("Your watchlist is empty.")
        else:
            msg = "📋 **Your Watchlist:**\n\n"
            for row in rows:
                msg += f"🆔 `{row[0]}` | {row[1]} | **₹{row[2]:,.2f}**\n"
            await update.message.reply_text(msg, parse_mode='Markdown')
        
        cursor.close()
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching list: {e}")

# 5. MAIN EXECUTION
if __name__ == "__main__":
    # Ensure Table exists in Aiven Cloud
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
        print("✅ Cloud Database Connected & Table Ready.")
    except Exception as e:
        print(f"❌ Initial Connection Error: {e}")

    # Final Verification of TOKEN
    FINAL_TOKEN = os.getenv("TELEGRAM_TOKEN", "8609572351:AAECJEKprX6iB7CsOIsm4S1Tlm-66PB-xps")
    
    # Start Bot
    app = ApplicationBuilder().token(FINAL_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("list", list_items))
    
    print("🤖 Bot is live and polling...")
    app.run_polling()