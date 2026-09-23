import asyncio
import os
import glob
import re
import sqlite3
import json
from aiohttp import web
from pyrogram import Client, filters

# Purane lock/session files clean karo
for session_file in glob.glob("*.session*"):
    try:
        os.remove(session_file)
    except Exception:
        pass

API_ID = 31169133
API_HASH = "b836f4b836df4cf83c2d475a5ad3b285"
BOT_TOKEN = "8947200389:AAE528tXpX5fGIodeSOacZFZILJVGCPCFrE"

# Database Init
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

# Pyrogram Client Setup
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

# Pyrogram Message Handler
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

# Web Server Handlers (aiohttp)
async def handle_home(request):
    return web.Response(text="7anime Backend Server Live!", status=200)

async def handle_get_episodes(request):
    anime_slug = request.query.get('anime', 'solo_leveling')
    season = int(request.query.get('season', 1))

    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT episode, msg_id, file_name FROM episodes 
        WHERE anime_slug = ? AND season = ? ORDER BY episode ASC
    ''', (anime_slug, season))
    rows = cursor.fetchall()
    conn.close()

    episodes = [{"ep": row[0], "msg_id": row[1], "file_name": row[2]} for row in rows]
    return web.json_response({"success": True, "episodes": episodes})

async def handle_stream_video(request):
    msg_id = int(request.match_info['msg_id'])
    is_download = request.query.get('download', '0')
    
    conn = sqlite3.connect('database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, file_name FROM episodes WHERE msg_id = ?', (msg_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return web.Response(text="Video not found in DB", status=404)

    target_chat_id = row[0]
    file_name = row[1] if row[1] else f"video_{msg_id}.mp4"

    headers = {
        'Content-Type': 'video/mp4',
        'Accept-Ranges': 'bytes',
    }

    # If 1-Click Download Requested
    if is_download == '1':
        headers['Content-Disposition'] = f'attachment; filename="{file_name}"'

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers=headers
    )
    await response.prepare(request)

    try:
        msg = await bot.get_messages(target_chat_id, msg_id)
        if msg:
            async for chunk in bot.stream_media(msg):
                await response.write(chunk)
    except Exception as e:
        print(f"Streaming error: {e}", flush=True)

    await response.write_eof()
    return response

# Main Entrypoint
async def main():
    app_web = web.Application()
    app_web.router.add_get('/', handle_home)
    app_web.router.add_get('/api/episodes', handle_get_episodes)
    app_web.router.add_get('/stream/{msg_id}', handle_stream_video)

    runner = web.AppRunner(app_web)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 5000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🚀 Web Server running on port {port}", flush=True)

    print("🚀 Starting Pyrogram Client...", flush=True)
    await bot.start()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Pyrogram Listener Active & Ready!", flush=True)

    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Server Stopped.")
        
