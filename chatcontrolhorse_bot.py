import os
import re
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import MessageEntityType 
from telegram.error import BadRequest # NEW: Needed to silently ignore invalid/user tags
from better_profanity import profanity

# --- 1. SETUP & SECURITY ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No token found! Make sure your .env file is set up correctly.")

# --- 2. CUSTOM WORD LISTS ---
SPAM_WORDS = ['scam', 'crypto', 'fake', 'bitcoin', 'investment']
HINDI_SLANGS = ['kutta', 'saala', 'kaminey', 'gadha', 'paagal', 'lauda','lund','madhar','chod', 'lode', 'mkc','chutiye','bhadwe','fuckyou']

# --- 3. ANTI-SPAM SETTINGS ---
SPAM_LIMIT = 5       # Max messages allowed...
SPAM_TIME = 10       # ...in this many seconds.
user_activity = {}   # The bot's memory for tracking message speed

profanity.load_censor_words()
profanity.add_censor_words(HINDI_SLANGS)

async def moderate_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This function evaluates every new text/document message in the group."""
    message = update.message

    # CHANGED: Removed "or not message.text" here so documents can pass through to the admin check
    if not message:
        return

    chat_id = message.chat_id
    user_id = message.from_user.id

    try:
        # --- RULE 1: ADMIN BYPASS ---
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status in ['administrator', 'creator']:
            return 

        # --- RULE 1.5: ANTI-DOCUMENT CHECK (NEW) ---
        if message.document:
            await message.delete()
            print(f"Deleted a document/pdf from {message.from_user.first_name}")
            return

        # Restoring the text check here for the remaining text-based rules
        if not message.text:
            return

        text_lower = message.text.lower()

        # --- RULE 2: ANTI-FLOOD CHECK ---
        current_time = time.time()
        if user_id not in user_activity:
            user_activity[user_id] = []

        user_activity[user_id] = [t for t in user_activity[user_id] if current_time - t < SPAM_TIME]
        user_activity[user_id].append(current_time)

        if len(user_activity[user_id]) > SPAM_LIMIT:
            await message.delete()
            print(f"Deleted spam flood from {message.from_user.first_name}")
            return

        # --- RULE 3: THE ULTIMATE LINK CHECKER ---
        # Part A: Use Telegram's built-in detector to catch formatted links and hidden URLs
        if message.entities:
            for entity in message.entities:
                if entity.type in [MessageEntityType.URL, MessageEntityType.TEXT_LINK]:
                    await message.delete()
                    print(f"Deleted a hidden/formatted link from {message.from_user.first_name}")
                    return

        # Part B: Upgraded Regex to catch sneaky t.me links just in case
        url_pattern = re.compile(r'http[s]?://|www\.|t\.me/|telegram\.me/|telegram\.dog/')
        if url_pattern.search(text_lower):
            await message.delete()
            print(f"Deleted a raw link from {message.from_user.first_name}")
            return

        # --- RULE 4: MENTION LOOKUP (CHANNEL/GROUP TAGS) ---
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.MENTION:
                    # Extract the exact @tag from the message
                    mention_text = message.text[entity.offset : entity.offset + entity.length]
                    
                    try:
                        # Ask Telegram what this tag actually is
                        chat_info = await context.bot.get_chat(mention_text)
                        
                        # If the tag points to a channel or group, nuke it!
                        if chat_info.type in ['channel', 'supergroup', 'group']:
                            await message.delete()
                            print(f"Deleted a channel/group mention ({mention_text}) from {message.from_user.first_name}")
                            return
                            
                    except BadRequest:
                        # If Telegram says "Chat not found" or "Bad Request", it's usually just a regular 
                        # user the bot hasn't met, or a made-up tag. Let the message stay.
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

if __name__ == '__main__':
    print("Waking up the bot...")
    
    # Keeping your PythonAnywhere proxy settings perfectly intact!
    app = Application.builder().token(TOKEN).proxy("http://proxy.server:3128").get_updates_proxy("http://proxy.server:3128").build()

    # CHANGED: Added filters.Document.ALL so the handler actually catches PDFs and files
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, moderate_messages))

    print("Bot is alive and watching the chat! Press Ctrl+C to stop it.")
    app.run_polling()