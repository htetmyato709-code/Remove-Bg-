import os
import io
import asyncio
import sqlite3
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from rembg import remove

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- Configuration -----------------
BOT_TOKEN = "8964042047:AAHcpeX9Lw0uEz77FuVWU1Tz3dpav-CB2w0"
OWNER_ID = 8305397892
# -------------------------------------------------

# SQLite Database Setup (User IDs သိမ်းဆည်းရန်)
DB_FILE = "bot_users.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

# User mode state storage
user_modes = {}  # {user_id: "rembg" or "hq"}

# Photo Enhancement Function
def enhance_image_quality(input_bytes: bytes) -> bytes:
    np_arr = np.frombuffer(input_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    # 1. Denoising
    denoised = cv2.fastNlMeansDenoisingColored(img, None, 6, 6, 7, 21)
    
    # 2. Sharpening
    gaussian = cv2.GaussianBlur(denoised, (0, 0), 2.0)
    sharpened = cv2.addWeighted(denoised, 1.5, gaussian, -0.5, 0)
    
    # 3. Contrast & Sharpness
    pil_img = Image.fromarray(cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB))
    
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.15)
    
    enhancer_sharpness = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharpness.enhance(1.2)
    
    output_io = io.BytesIO()
    pil_img.save(output_io, format="PNG", quality=100)
    output_io.seek(0)
    return output_io.getvalue()

# /start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("🖼️ Remove Background", callback_data="mode_rembg"),
            InlineKeyboardButton("✨ High Quality", callback_data="mode_hq"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"မင်္ဂလာပါ {update.effective_user.first_name}!\n\n"
        "အောက်ပါ Button များထဲမှ သင်အသုံးပြုလိုသော Feature ကို ရွေးချယ်ပါ 👇"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# Button Callback Handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    add_user(user_id)
    
    if query.data == "mode_rembg":
        user_modes[user_id] = "rembg"
        await query.edit_message_text(
            "✅ **Remove Background** Mode ကို ရွေးချယ်ထားပါသည်။\n\n"
            "Background ဖျောက်လိုသော ဓာတ်ပုံကို ပို့ပေးပါ။",
            parse_mode="Markdown"
        )
    elif query.data == "mode_hq":
        user_modes[user_id] = "hq"
        await query.edit_message_text(
            "✅ **High Quality** Mode ကို ရွေးချယ်ထားပါသည်။\n\n"
            "Quality မြှင့်တင်လိုသော ဓာတ်ပုံကို ပို့ပေးပါ။",
            parse_mode="Markdown"
        )

# Photo Handler (Fixed Error)
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)
    
    current_mode = user_modes.get(user_id)
    if not current_mode:
        keyboard = [
            [
                InlineKeyboardButton("🖼️ Remove Background", callback_data="mode_rembg"),
                InlineKeyboardButton("✨ High Quality", callback_data="mode_hq"),
            ]
        ]
        await update.message.reply_text(
            "ကျေးဇူးပြု၍ Feature အရင်ရွေးချယ်ပေးပါ 👇",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    status_msg = await update.message.reply_text("⏳ ပုံကို Process လုပ်နေပါသည်... ခေတ္တစောင့်ပေးပါ။")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        raw_bytes = await photo_file.download_as_bytearray()
        photo_bytes = bytes(raw_bytes)  # Fix bytearray to bytes
        
        loop = asyncio.get_running_loop()
        
        if current_mode == "rembg":
            # AI Background Removal (bytes convert)
            processed_bytes = await loop.run_in_executor(None, lambda: remove(photo_bytes))
            caption = "✅ Background ဖျောက်လုပ်ဆောင်ချက် ပြီးပါပြီ။"
        elif current_mode == "hq":
            # Image Enhancement
            processed_bytes = await loop.run_in_executor(None, enhance_image_quality, photo_bytes)
            caption = "✅ Premium Quality မြှင့်တင်ပေးထားပါသည်။"
            
        await status_msg.delete()
        
        # Transparent background မပျက်စေရန် PNG Document အနေဖြင့် ပို့ပေးခြင်း
        await update.message.reply_document(
            document=io.BytesIO(processed_bytes),
            filename="output.png",
            caption=caption
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error ဖြစ်ပေါ်သွားပါသည်: {str(e)}")

# Owner Broadcast Command (/post သို့မဟုတ် /broadcast)
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("⛔ သင်သည် Owner မဟုတ်ပါသဖြင့် ဤ Command ကို အသုံးပြု၍မရပါ။")
        return
        
    if not context.args:
        await update.message.reply_text(
            "⚠️ ပို့လိုသော စာသားကို command နောက်တွင် ထည့်ပေးပါ။\n\n"
            "ဥပမာ - `/post မင်္ဂလာပါ User များခင်ဗျာ...`",
            parse_mode="Markdown"
        )
        return
        
    broadcast_msg = " ".join(context.args)
    users = get_all_users()
    count = 0
    
    status_msg = await update.message.reply_text(f"📢 Users ({len(users)}) ယောက်ထံ Message စတင်ပို့နေပါသည်...")
    
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_msg)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            continue
            
    await status_msg.edit_text(f"✅ Users စုစုပေါင်း ({count}) ယောက်ထံ Post ပို့ပြီးပါပြီ။")

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("post", broadcast))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
