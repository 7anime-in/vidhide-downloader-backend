import asyncio
import os
import glob

# Startup par purani session files remove karna taaki Render par lock crash na ho
for session_file in glob.glob("*.session*"):
    try:
        os.remove(session_file)
    except Exception:
        pass

# Fix asyncio event loop issue
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import re
import queue
import sqlite3
import threading
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pyrogram import Client, filters

# -------------------------------------------------------------
# TELEGRAM BOT CREDENTIALS
# -------------------------------------------------------------
API_ID = 31169133
API_HASH = "b836f4b836df4cf83c2d475a5ad3b285"
BOT_TOKEN = "8947200389:AAE528tXpX5fGIodeSOacZFZILJVGCPCFrE"

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_slug TEXT,
            season INTEGER,
            episode INTEGER,
            chat_id INTEGER,
            msg_id INTEGER UNIQUE,
            file_id TEXT,
            file_name TEXT
        )
    ''')
    
    # Auto-add chat_id column if upgrading from old DB
    cursor.execute("PRAGMA table_info(episodes)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'chat_id' not in columns:
        try:
            cursor.execute("ALTER TABLE episodes ADD COLUMN chat_id INTEGER")
        except Exception:
            pass
            
    conn.commit()
    conn.close()

init_db()

# in_memory=True prevents SQLite session lock issues on cloud hostings
bot = Client(
    name="7anime_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# -------------------------------------------------------------
# TITLE CLEANING & PARSING LOGIC
# -------------------------------------------------------------
def clean_universal_title(text):
    if not text:
        return ""
    text = text.replace(".", " ").replace("_", " ")
    text = re.sub(
        r"(?:1080p|720p|480p|4k|x265|x264|10bit|BluRay|HDR|WEB-DL|Dual|Audio|ESub|FHD|HD|RareToonsIndia|Hindi|English|Sub|Dub|Multi|\.mkv|\.mp4)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    text = re.sub(
        r"(?:S\d+E\d+|Season\s*\d+|Episode\s*\d+|\bEp\s*\d+|\bE\s*\d+\b)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[-_@#|:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def parse_anime_info(message):
    caption = message.caption or ""
    filename = ""
    if message.video and message.video.file_name:
        filename = message.video.file_name
    elif message.document and message.document.file_name:
        filename = message.document.file_name

    forward_name = ""
    if message.forward_from_chat and message.forward_from_chat.title:
        forward_name = message.forward_from_chat.title

    combined_text = f"{caption}\n{filename}\n{forward_name}"

    anime_name = ""
    anime_match = re.search(r"(?:ANIME|Anime|Title)[:\s-]+\s*(.+)", caption, re.IGNORECASE)
    if anime_match:
        raw_found = anime_match.group(1).split("\n")[0]
        anime_name = clean_universal_title(raw_found)

    if not anime_name or len(anime_name) < 2:
        target_str = filename if filename else caption
        cleaned_file = clean_universal_title(target_str)
        if cleaned_file and not any(w in cleaned_file.lower() for w in ["otaku", "provider", "bot", "stream"]):
            anime_name = cleaned_file

    if not anime_name or len(anime_name) < 2:
        anime_name = "solo_leveling"

    anime_slug = re.sub(r"[^\w\s-]", "", anime_name).strip().lower()
    anime_slug = re.sub(r"[-\s]+", "_", anime_slug)

    season_num = 1
    season_match = re.search(r"(?:Season|S)[\s:-]*0*(\d+)", combined_text, re.IGNORECASE)
    if season_match:
        season_num = int(season_match.group(1))

    episode_num = None
    se_match = re.search(r"S\d+E(\d+)", combined_text, re.IGNORECASE)
    if se_match:
        episode_num = int(se_match.group(1))
    else:
        ep_match = re.search(r"(?:Episode|Ep|E)[\s.-]*0*(\d+)", combined_text, re.IGNORECASE)
        if ep_match:
            episode_num = int(ep_match.group(1))

    return anime_slug, season_num, episode_num

# -------------------------------------------------------------
# DYNAMIC BOT LISTENER (CHANNEL & PRIVATE DM)
# -------------------------------------------------------------
@bot.on_message((filters.channel | filters.private) & (filters.video | filters.document))
async def handle_incoming_videos(client, message):
    chat_id = message.chat.id
    print(f" [LOG] Video received | Chat ID: {chat_id} | Msg ID: {message.id}")
    caption = message.caption or ""
    
    clean_channel_id = str(chat_id).replace("-100", "")
    msg_link = f"https://t.me/c/{clean_channel_id}/{message.id}" if message.chat.type != "private" else "Private Chat"

    # Bulk Indexing
    bulk_match = re.search(r"/?bulk\s+([a-zA-Z0-9_-]+)\s+(\d+)\s+(\d+)", caption, re.IGNORECASE)
    if bulk_match:
        anime_slug = bulk_match.group(1).lower()
        season = int(bulk_match.group(2))
        total_count = int(bulk_match.group(3))
        first_msg_id = message.id

        conn = sqlite3.connect('database.db', check_same_thread=False)
        cursor = conn.cursor()

        saved_count = 0
        current_ep = 1
        current_msg_id = first_msg_id

        while saved_count < total_count and (current_msg_id - first_msg_id) < (total_count * 3):
            try:
                target_msg = await bot.get_messages(chat_id, current_msg_id)
                if target_msg and (target_msg.video or target_msg.document):
                    media_item = target_msg.video or target_msg.document
                    f_id = media_item.file_id
                    f_name = getattr(media_item, 'file_name', f"{anime_slug}_S{season}E{current_ep}.mp4")

                    cursor.execute('''
                        INSERT OR REPLACE INTO episodes (anime_slug, season, episode, chat_id, msg_id, file_id, file_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (anime_slug, season, current_ep, chat_id, target_msg.id, f_id, f_name))
                    
                    saved_count += 1
                    current_ep += 1
            except Exception as e:
                print(f"Error indexing msg {current_msg_id}: {e}")
            
            current_msg_id += 1

        conn.commit()
        conn.close()

        await message.reply_text(
            f"✅ **Bulk Indexing Complete!**\n\n"
            f"🎬 **Anime Slug:** `{anime_slug}`\n"
            f"📌 **Season:** `{season}` | **Total Saved:** `{saved_count}`",
            disable_web_page_preview=True
        )
        return

    # Single Video Indexing
    anime_slug, season, episode = parse_anime_info(message)

    if episode is not None:
        media = message.video or message.document
        f_id = media.file_id
        file_name = getattr(media, 'file_name', f"{anime_slug}_S{season}E{episode}.mp4")

        conn = sqlite3.connect('database.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO episodes (anime_slug, season, episode, chat_id, msg_id, file_id, file_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (anime_slug, season, episode, chat_id, message.id, f_id, file_name))
        conn.commit()
        conn.close()

        reply_text = (
            f"✅ **Video Indexed Successfully!**\n\n"
            f"🎬 **Anime Name:** `{anime_slug}`\n"
            f"📌 **Season:** `{season}` | **Episode:** `{episode}`\n"
            f"🆔 **Msg ID:** `{message.id}`\n\n"
            f"🔗 **Video Link:** {msg_link}"
        )
        await message.reply_text(reply_text, disable_web_page_preview=True)

# -------------------------------------------------------------
# FRONTEND API ENDPOINTS
# -------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return "7anime Backend Server Live!"

@app.route('/api/episodes', methods=['GET'])
def get_episodes():
    anime_slug = request.args.get('anime', 'solo_leveling')
    season = request.args.get('season', 1, type=int)

    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT episode, msg_id, file_name FROM episodes 
        WHERE anime_slug = ? AND season = ? ORDER BY episode ASC
    ''', (anime_slug, season))
    rows = cursor.fetchall()
    conn.close()

    episodes = [{"ep": row[0], "msg_id": row[1], "file_name": row[2]} for row in rows]
    return jsonify({"success": True, "episodes": episodes})

@app.route('/stream/<int:msg_id>', methods=['GET'])
def stream_video(msg_id):
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM episodes WHERE msg_id = ?', (msg_id,))
    row = cursor.fetchone()
    conn.close()

    target_chat_id = row[0] if row and row[0] else None

    def generate():
        chunk_queue = queue.Queue()

        async def producer():
            try:
                if target_chat_id:
                    msg = await bot.get_messages(target_chat_id, msg_id)
                    if msg:
                        async for chunk in bot.stream_media(msg):
                            chunk_queue.put(chunk)
            except Exception as e:
                print(f"Streaming error: {e}")
            finally:
                chunk_queue.put(None)

        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(producer(), loop)
        else:
            chunk_queue.put(None)

        while True:
            chunk = chunk_queue.get()
            if chunk is None:
                break
            yield chunk

    return Response(generate(), mimetype='video/mp4')

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

async def main():
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print("🚀 Starting Pyrogram Client...")
    try:
        await bot.start()
        print("🧹 Clearing Webhook configuration...")
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Pyrogram Listener is active and running!")
    except Exception as e:
        print(f"❌ Pyrogram Start Error: {e}")

    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
    
