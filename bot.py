from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlite3
# Import the initialization function from your other file
from database import init_db 

TOKEN = '8543572699:AAEQkrW8GfVcDJhIpdwMKU2KussdhwC0SJA'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Added debug print to verify the bot is alive
    print(f"Received /start from {update.message.from_user.username}") 
    
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    
    conn = sqlite3.connect('tracker.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Users (telegram_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        await update.message.reply_text(f"Welcome {username}! You are now registered.")
    except sqlite3.IntegrityError:
        await update.message.reply_text(f"Welcome back, {username}!")
    finally:
        conn.close()

if __name__ == '__main__':
    # Initialize database tables first [cite: 45]
    init_db() 
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("Bot is running... Press Ctrl+C to stop.")
    app.run_polling()