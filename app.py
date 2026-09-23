import asyncio
import sys

# --- FIX FOR PYTHON 3.10+ EVENT LOOP CRASH ---
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import glob
import re
import queue
import sqlite3
import threading
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pyrogram import Client, filters

# Purane lock files clean karo
for session_file in glob.glob("*.session*"):
    try:
        os.remove(session_file)
    except Exception:
        pass

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

# Pyrogram bot in-memory setup
bot = Client(
    name="7anime_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

def clean_universal_title(text):
    if not text:
        return ""
    text = text.replace(".", " ").replace("_", " ")
    text = re.sub(
        r"(?:1080p|720p|480p|4k|x265|x264|10bit|BluRay|HDR|WEB-DL|Dual|Audio|ESub|FHD|HD|RareToonsIndia|Hindi|English|Sub|Dub|Multi|\.mkv|\.mp4)",
        "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text)
    text = re.sub(
        r"(?:S\d+E\d+|Season\s*\d+|Episode\s*\d+|\bEp\s*\d+|\bE\s*\d+\b)",
        "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[-_@#|:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def parse_anime_info(message):
    caption = message.caption or ""
    filename = ""
    if message.video:
        filename = getattr(message.video, 'file_name', '') or ""
    elif message.document:
        filename = getattr(message.document, 'file_name', '') or ""

    forward_name = ""
    if message.forward_from_chat and message.forward_from_chat.title:
        forward_name = message.forward_from_chat.title

    combined_text = f"{caption} {filename} {forward_name}".strip()

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

    episode_num = 1
    se_match = re.search(r"S\d+E(\d+)", combined_text, re.IGNORECASE)
    if se_match:
        episode_num = int(se_match.group(1))
    else:
        ep_match = re.search(r"(?:Episode|Ep|E)[\s.-]*0*(\d+)", combined_text, re.IGNORECASE)
        if ep_match:
            episode_num = int(ep_match.group(1))

    return anime_slug, season_num, episode_num

# Bot Listener
@bot.on_message((filters.channel | filters.private | filters.group) & (filters.video | filters.document))
async def handle_incoming_videos(client, message):
    chat_id = message.chat.id
    print(f" [LOG] Video received in Chat ID: {chat_id} | Msg ID: {message.id}", flush=True)

    clean_channel_id = str(chat_id).replace("-100", "")
    msg_link = f"https://t.me/c/{clean_channel_id}/{message.id}" if message.chat.type != "private" else "Private Chat"

    anime_slug, season, episode = parse_anime_info(message)

    media = message.video or message.document
    f_id = media.file_id
    file_name = getattr(media, 'file_name', '') or f"{anime_slug}_S{season}E{episode}.mp4"

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

    try:
        await client.send_message(chat_id=chat_id, text=reply_text, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error sending reply: {e}", flush=True)

# Flask Endpoints
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
    is_download = request.args.get('download', '0')
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, file_name FROM episodes WHERE msg_id = ?', (msg_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "Video not found in DB", 404

    target_chat_id = row[0]
    file_name = row[1] if row[1] else f"video_{msg_id}.mp4"

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
                print(f"Streaming error: {e}", flush=True)
            finally:
                chunk_queue.put(None)

        loop = getattr(bot, 'loop', None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(producer(), loop)
        else:
            chunk_queue.put(None)

        while True:
            chunk = chunk_queue.get()
            if chunk is None:
                break
            yield chunk

    headers = {}
    if is_download == '1':
        headers['Content-Disposition'] = f'attachment; filename="{file_name}"'

    return Response(generate(), mimetype='video/mp4', headers=headers)

def start_pyrogram():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.loop = loop
    
    async def run_bot():
        print("🚀 Starting Pyrogram Client...", flush=True)
        await bot.start()
        print("✅ Pyrogram Listener Active & Ready!", flush=True)
        await asyncio.Event().wait()

    loop.run_until_complete(run_bot())

def init_bot_thread():
    if not any(t.name == "PyrogramBotThread" for t in threading.enumerate()):
        t = threading.Thread(target=start_pyrogram, daemon=True, name="PyrogramBotThread")
        t.start()

init_bot_thread()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
                                            
