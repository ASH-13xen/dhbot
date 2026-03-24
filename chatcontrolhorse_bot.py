import os
import re
import time
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import MessageEntityType
from telegram.error import BadRequest
from better_profanity import profanity

# --- 1. SETUP & SECURITY ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No token found! Make sure your .env file or Render Environment Variables are set up correctly.")

# --- 2. CUSTOM WORD LISTS ---
SPAM_WORDS = ['scam', 'crypto', 'fake', 'bitcoin', 'investment']
HINDI_SLANGS = ['kutta', 'saala', 'kaminey', 'gadha', 'paagal', 'lauda','lund','madhar','chod', 'lode', 'mkc','chutiye','bhadwe','fuckyou']

# --- 3. ANTI-SPAM SETTINGS ---
SPAM_LIMIT = 1       # Max messages allowed...
SPAM_TIME = 300      # ...in this many seconds (300s = 5 minutes).
user_activity = {}   # The bot's memory for tracking message speed

profanity.load_censor_words()
profanity.add_censor_words(HINDI_SLANGS)

async def moderate_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This function evaluates every new text/document/image message in the group."""
    message = update.message

    if not message:
        return

    chat_id = message.chat_id
    user_id = message.from_user.id

    try:
        # --- RULE 1: ADMIN BYPASS ---
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status in ['administrator', 'creator']:
            return

        # --- RULE 1.5: ANTI-DOCUMENT CHECK ---
        if message.document:
            await message.delete()
            print(f"Deleted a document/pdf from {message.from_user.first_name}")
            return

        # --- RULE 2: ANTI-FLOOD CHECK (Moved up so images trigger the timer too) ---
        current_time = time.time()
        if user_id not in user_activity:
            user_activity[user_id] = []

        user_activity[user_id] = [t for t in user_activity[user_id] if current_time - t < SPAM_TIME]
        user_activity[user_id].append(current_time)

        if len(user_activity[user_id]) > SPAM_LIMIT:
            await message.delete()
            print(f"Deleted spam flood from {message.from_user.first_name}")
            return

        # Handle both regular text and image captions
        msg_text = message.text or message.caption
        if not msg_text:
            return

        text_lower = msg_text.lower()
        msg_entities = message.entities or message.caption_entities

        # --- RULE 3: THE ULTIMATE LINK CHECKER ---
        if msg_entities:
            for entity in msg_entities:
                if entity.type in [MessageEntityType.URL, MessageEntityType.TEXT_LINK]:
                    await message.delete()
                    print(f"Deleted a hidden/formatted link from {message.from_user.first_name}")
                    return

        url_pattern = re.compile(r'http[s]?://|www\.|t\.me/|telegram\.me/|telegram\.dog/')
        if url_pattern.search(text_lower):
            await message.delete()
            print(f"Deleted a raw link from {message.from_user.first_name}")
            return

        # --- RULE 4: MENTION LOOKUP (CHANNEL/GROUP TAGS) ---
        if msg_entities:
            for entity in msg_entities:
                if entity.type == MessageEntityType.MENTION:
                    mention_text = msg_text[entity.offset : entity.offset + entity.length]
                    try:
                        chat_info = await context.bot.get_chat(mention_text)
                        if chat_info.type in ['channel', 'supergroup', 'group']:
                            await message.delete()
                            print(f"Deleted a channel/group mention ({mention_text}) from {message.from_user.first_name}")
                            return
                    except BadRequest:
                        pass

        # --- RULE 5: BAD WORDS (English + Hindi) ---
        if profanity.contains_profanity(text_lower):
            await message.delete()
            print(f"Deleted profanity/slang from {message.from_user.first_name}")
            return

        # --- RULE 6: CUSTOM SPAM WORDS ---
        if any(word in text_lower for word in SPAM_WORDS):
            await message.delete()
            print(f"Deleted a custom spam word from {message.from_user.first_name}")
            return

    except Exception as e:
        print(f"Oops, an error occurred: {e}")


# --- NEW: DUMMY WEB SERVER FOR RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running beautifully!"

def run_web():
    # Render assigns a port dynamically via the PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


if __name__ == '__main__':
    print("Starting the dummy web server...")
    # 1. Start the Flask server in a separate background thread
    threading.Thread(target=run_web, daemon=True).start()

    print("Waking up the bot...")
    # 2. Set up your bot (PythonAnywhere proxy completely removed!)
    app = Application.builder().token(TOKEN).build()
    
    # CHANGED: Added filters.PHOTO so normal images are passed to the moderator
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND, moderate_messages))

    print("Bot is alive and watching the chat! Press Ctrl+C to stop it.")
    # 3. Run the polling loop in the main thread
    app.run_polling()
