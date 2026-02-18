import yt_dlp
import subprocess
import os
import re
import glob
import asyncio
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

def get_user_identifier(update):
    user = update.effective_user
    if not user: return "Unknown"
    return user.username if user.username else f"ID:{user.id}"

def get_ydl_opts(mode="video"):
    import os
    from pathlib import Path
    Path("downloads").mkdir(exist_ok=True)
    
    # IMPORTANTE: Usamos 'node' (el nombre corto) para evitar problemas de rutas con espacios
    node_exe = 'node' 

    cookie_path = r"C:\BOT\www.youtube.com_cookies.txt"

    opts = {
        'outtmpl': 'downloads/%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': False,
        'no_warnings': False,
        
        # 1. MOTOR JS (Aseguramos el comando corto)
        'js_runtime': node_exe,
        
        # 2. CLIENTE ANDROID: Es el que mejor funciona cuando el n-challenge falla en PC
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['po_token']
            }
        },
        
        # 3. COOKIES
        'cookiefile': cookie_path,

        'headers': {
            'User-Agent': 'com.google.android.youtube/19.05.36 (Linux; U; Android 14; es_ES; Pixel 7 Build/UQ1A.240205.002) gzip',
        }
    }

    if mode == "audio":
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Formato 18 es el que bajó bien en tu consola
        opts['format'] = '18/best'
    
    return opts

async def download_media(url, mode="video"):
    from pathlib import Path
    Path("downloads").mkdir(exist_ok=True)
    
    cookie_path = r"C:\BOT\www.youtube.com_cookies.txt"
    # Usamos un nombre fijo temporal para facilitar la compresión si es necesaria
    temp_output = os.path.join("downloads", "temp_video.%(ext)s")
    
    command = [
        "yt-dlp",
        "--rm-cache-dir",
        "--js-runtime", "node",
        "--cookies", cookie_path,
        "-f", "18/best[ext=mp4]/best",
        "--output", temp_output,
        url
    ]

    if mode == "audio":
        command.extend(["-x", "--audio-format", "mp3"])

    try:
        print(f"--- [EJECUTANDO DESCARGA] ---")
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process.communicate()

        # Localizar el archivo descargado
        files = glob.glob(os.path.join("downloads", "temp_video.*"))
        if not files: return None
        file_path = files[0]

        # --- LÓGICA DE COMPRESIÓN SI ES VIDEO ---
        if mode == "video":
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            if file_size_mb > 50:
                print(f"⚠️ Archivo de {file_size_mb:.1f}MB demasiado grande. Comprimiendo...")
                compressed_path = os.path.join("downloads", "video_comprimido.mp4")
                
                # Comando FFmpeg para comprimir (reducimos bitrate a 1MB/s aprox)
                # Ajustamos la escala a 480p máximo para asegurar que baje el peso
                compress_command = [
                    "ffmpeg", "-y", "-i", file_path,
                    "-vcodec", "libx264", "-crf", "28", 
                    "-preset", "faster", "-vf", "scale=-2:480",
                    "-acodec", "aac", "-b:a", "128k",
                    compressed_path
                ]
                
                comp_process = await asyncio.create_subprocess_exec(*compress_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await comp_process.communicate()
                
                # Reemplazamos el original por el comprimido si tuvo éxito
                if os.path.exists(compressed_path):
                    os.remove(file_path)
                    file_path = compressed_path
                    new_size = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"✅ Compresión finalizada: {new_size:.1f}MB")
                    
                    if new_size > 50:
                        print("❌ Sigue siendo demasiado grande tras comprimir.")
                        # Aquí el bot lanzará el error de "Entity Too Large" o puedes manejarlo tú

        return file_path

    except Exception as e:
        print(f"🔥 Error: {e}")
        return None

async def handle_youtube_search(update: Update, context, format_type=None, offset=0):
    try:
        from bot_main import user_manager
    except ImportError:
        user_manager = None

    is_callback = update.callback_query is not None
    if is_callback:
        query_text = update.callback_query.message.text
        search_query = query_text.replace('🔍 Resultados para: ', '').split('\n')[0].strip()
    else:
        text = update.message.text
        search_query = re.sub(r'^/(mp3|video)\s*', '', text).strip()

    if not search_query: return

    is_url = search_query.startswith('http')

    if not is_callback and (format_type or update.message.text.startswith('/')) and is_url:
        tipo = "audio" if (format_type == "mp3" or update.message.text.startswith('/mp3')) else "video"
        u_name = get_user_identifier(update)
        chat = update.effective_chat
        label = "PRIVADO" if chat.type == "private" else f"GRUPO:{chat.title[:15]}"
        if user_manager:
            user_manager.log(u_name, f"DIRECT_{tipo.upper()}", search_query, origen=label)

        wait_msg = await update.message.reply_text(f"🚀 Procesando {tipo}...")
        path = await download_media(search_query, mode=tipo)
        
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                if tipo == "audio": await update.message.reply_audio(audio=f)
                else: await update.message.reply_video(video=f)
            os.remove(path)
            await wait_msg.delete()
        else:
            await wait_msg.edit_text("❌ Error al descargar. Es posible que el video no esté disponible.")
        return

    wait_msg = None
    if not is_callback:
        wait_msg = await update.message.reply_text(f"🔍 Buscando <b>{search_query}</b>...", parse_mode='HTML')

    try:
        limit = 5
        search_limit = offset + limit + 1
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            search_trigger = f"ytsearch{search_limit}:{search_query}" if not is_url else search_query
            search_result = await loop.run_in_executor(None, lambda: ydl.extract_info(search_trigger, download=False))
            all_entries = search_result.get('entries', [search_result])
        
        entries = all_entries[offset:offset + limit]
        if not entries or not entries[0]:
            if is_callback: await update.callback_query.answer("❌ Sin resultados.")
            else: await wait_msg.edit_text("❌ Sin resultados.")
            return

        keyboard = []
        for entry in entries:
            if not entry: continue
            v_id = entry.get('id')
            title = (entry.get('title')[:45] + "..") if entry.get('title') else "Video"
            keyboard.append([InlineKeyboardButton(f"📺 {title}", callback_data="ignore")])
            keyboard.append([
                InlineKeyboardButton("🎵 MP3", callback_data=f"yt_audio_{v_id}"),
                InlineKeyboardButton("🎥 Video", callback_data=f"yt_video_{v_id}")
            ])

        nav_buttons = []
        if offset > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"yt_page_{offset-limit}"))
        if len(all_entries) > offset + limit: nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"yt_page_{offset+limit}"))
        if nav_buttons: keyboard.append(nav_buttons)

        text_display = f"🔍 Resultados para: <b>{search_query}</b>"
        if is_callback: 
            await update.callback_query.edit_message_text(text_display, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        else:
            if wait_msg: await wait_msg.delete()
            await update.message.reply_text(text_display, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    except Exception as e:
        print(f"Error búsqueda: {e}")
        if wait_msg: await wait_msg.edit_text("❌ Error en la búsqueda.")

async def media_callback_handler(update: Update, context):
    try: from bot_main import user_manager 
    except: user_manager = None

    query = update.callback_query
    data = query.data
    if data == "ignore": return await query.answer()
    
    if data.startswith("yt_page_"):
        await query.answer()
        return await handle_youtube_search(update, context, offset=int(data.split("_")[2]))

    await query.answer()
    try:
        _, mode, video_id = data.split("_", 2)
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        
        if user_manager:
            user_manager.log(get_user_identifier(update), f"BOTON_{mode.upper()}", video_id)

        await query.edit_message_text(f"⏳ Procesando <b>{mode.upper()}</b>...", parse_mode='HTML')
        path = await download_media(full_url, mode=("audio" if mode == "audio" else "video"))
        
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                if mode == "audio": await query.message.reply_audio(audio=f)
                else: await query.message.reply_video(video=f)
            os.remove(path)
            await query.message.delete()
        else:
            await query.message.reply_text("❌ No se pudo descargar el video.")
    except Exception as e:
        print(f"Error en callback: {e}")
        await query.message.reply_text("❌ Error al procesar la descarga.")