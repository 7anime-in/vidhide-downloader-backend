import os
import re
import sqlite3
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pyrogram import Client, filters

# -------------------------------------------------------------
# YOUR CREDENTIALS & CHANNEL ID
# -------------------------------------------------------------
API_ID = 31169133
API_HASH = "b836f4b836df4cf83c2d475a5ad3b285"
BOT_TOKEN = "8947200389:AAEhBe-mIYrnG4D26j0rksI5ztR_Jje8O9I"
CHANNEL_ID = -1002566941795

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_slug TEXT,
            season INTEGER,
            episode INTEGER,
            msg_id INTEGER UNIQUE,
            file_id TEXT,
            file_name TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

bot = Client("7anime_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------------------------------------------
# AUTO CAPTION & TITLE CLEANING LOGIC (FROM YOUR MAIN.PY)
# -------------------------------------------------------------
def clean_universal_title(text):
    if not text:
        return ""
    text = text.replace(".", " ").replace("_", " ")
    # Clean unnecessary quality tags, codecs, audio, extension noise
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

    # 1. Extract Clean Anime Name
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

    # Make URL-friendly slug (e.g. "Solo Leveling" -> "solo_leveling")
    anime_slug = re.sub(r"[^\w\s-]", "", anime_name).strip().lower()
    anime_slug = re.sub(r"[-\s]+", "_", anime_slug)

    # 2. Extract Season
    season_num = 1
    season_match = re.search(r"(?:Season|S)[\s:-]*0*(\d+)", combined_text, re.IGNORECASE)
    if season_match:
        season_num = int(season_match.group(1))

    # 3. Extract Episode
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
# AUTOMATIC CHANNEL LISTENER (AUTO-CAPTION INDEXING)
# -------------------------------------------------------------
@bot.on_message(filters.chat(CHANNEL_ID) & (filters.video | filters.document))
async def handle_incoming_videos(client, message):
    caption = message.caption or ""
    
    # Check for /bulk command in caption (e.g., /bulk solo_leveling 1 12)
    bulk_match = re.search(r"/?bulk\s+([a-zA-Z0-9_-]+)\s+(\d+)\s+(\d+)", caption, re.IGNORECASE)
    
    if bulk_match:
        anime_slug = bulk_match.group(1).lower()
        season = int(bulk_match.group(2))
        total_count = int(bulk_match.group(3))
        first_msg_id = message.id

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        saved_count = 0
        current_ep = 1
        current_msg_id = first_msg_id

        while saved_count < total_count and (current_msg_id - first_msg_id) < (total_count * 3):
            try:
                target_msg = await bot.get_messages(CHANNEL_ID, current_msg_id)
                if target_msg and (target_msg.video or target_msg.document):
                    media_item = target_msg.video or target_msg.document
                    f_id = media_item.file_id
                    f_name = getattr(media_item, 'file_name', f"{anime_slug}_S{season}E{current_ep}.mp4")

                    cursor.execute('''
                        INSERT OR REPLACE INTO episodes (anime_slug, season, episode, msg_id, file_id, file_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (anime_slug, season, current_ep, target_msg.id, f_id, f_name))
                    
                    saved_count += 1
                    current_ep += 1
            except Exception:
                pass
            
            current_msg_id += 1

        conn.commit()
        conn.close()
        print(f"✅ Bulk Auto Indexing Done: {anime_slug} Season {season} ({saved_count} Episodes)")
        return

    # Auto Parser from main.py
    anime_slug, season, episode = parse_anime_info(message)

    if episode is not None:
        media = message.video or message.document
        f_id = media.file_id
        file_name = getattr(media, 'file_name', f"{anime_slug}_S{season}E{episode}.mp4")

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO episodes (anime_slug, season, episode, msg_id, file_id, file_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (anime_slug, season, episode, message.id, f_id, file_name))
        conn.commit()
        conn.close()
        print(f"✅ Smart Auto-Indexed: {anime_slug} | S{season}E{episode} | Msg ID: {message.id}")

# -------------------------------------------------------------
# FRONTEND API ENDPOINTS
# -------------------------------------------------------------
@app.route('/api/episodes', methods=['GET'])
def get_episodes():
    anime_slug = request.args.get('anime', 'solo_leveling')
    season = request.args.get('season', 1, type=int)

    conn = sqlite3.connect('database.db')
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
    async def generate():
        async with bot:
            msg = await bot.get_messages(CHANNEL_ID, msg_id)
            async for chunk in bot.stream_media(msg):
                yield chunk

    return Response(generate(), mimetype='video/mp4')

if __name__ == '__main__':
    bot.start()
    app.run(host='0.0.0.0', port=5000)
    
