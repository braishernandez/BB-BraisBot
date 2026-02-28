import yt_dlp
import subprocess
import os
import re
import glob
import asyncio
import io
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

def get_user_identifier(update: Update):
    user = update.effective_user
    if not user: return "Unknown"
    return user.username if user.username else f"ID:{user.id}"

def get_ydl_opts(mode="video"):
    Path("downloads").mkdir(exist_ok=True)
    node_exe = 'node' 
    cookie_path = r"C:\BOT\www.youtube.com_cookies.txt"

    opts = {
        'outtmpl': 'downloads/%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': False,
        'no_warnings': False,
        'js_runtime': node_exe,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['po_token']
            }
        },
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
        opts['format'] = '18/best'
    
    return opts

async def download_media(url, mode="video"):
    Path("downloads").mkdir(exist_ok=True)
    cookie_path = r"C:\BOT\www.youtube.com_cookies.txt"
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

        files = glob.glob(os.path.join("downloads", "temp_video.*"))
        if not files: return None
        file_path = files[0]

        if mode == "video":
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 50:
                print(f"⚠️ Archivo de {file_size_mb:.1f}MB demasiado grande. Comprimiendo...")
                compressed_path = os.path.join("downloads", "video_comprimido.mp4")
                
                compress_command = [
                    "ffmpeg", "-y", "-i", file_path,
                    "-vcodec", "libx264", "-crf", "28", 
                    "-preset", "faster", "-vf", "scale=-2:480",
                    "-acodec", "aac", "-b:a", "128k",
                    compressed_path
                ]
                
                comp_process = await asyncio.create_subprocess_exec(*compress_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await comp_process.communicate()
                
                if os.path.exists(compressed_path):
                    os.remove(file_path)
                    file_path = compressed_path
                    new_size = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"✅ Compresión finalizada: {new_size:.1f}MB")

        return file_path

    except Exception as e:
        print(f"🔥 Error en download_media: {e}")
        return None

async def handle_youtube_search(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type=None, offset=0, query_override=None):
    try:
        from bot_main import user_manager
    except ImportError:
        user_manager = None

    is_callback = update.callback_query is not None
    
    if query_override:
        search_query = query_override
    elif is_callback:
        query_text = update.callback_query.message.text
        search_query = query_text.replace('🔍 Resultados para: ', '').split('\n')[0].strip()
    else:
        text = update.message.text
        search_query = re.sub(r'^/(mp3|video)\s*', '', text).strip()

    if not search_query: return

    is_url = search_query.startswith(('http://', 'https://'))

    # 2. CASO: DESCARGA DIRECTA
    if not is_callback and is_url:
        cmd = update.message.text.split()[0].lower() if update.message.text else ""
        tipo = "audio" if (format_type == "mp3" or "/mp3" in cmd) else "video"
        
        u_name = get_user_identifier(update)
        chat = update.effective_chat
        label = "PRIVADO" if chat.type == "private" else f"GRUPO:{chat.title[:15]}"
        
        if user_manager:
            user_manager.log(u_name, f"DIRECT_{tipo.upper()}", search_query, origen=label)

        wait_msg = await update.message.reply_text(f"🚀 Procesando {tipo}...")
        path = await download_media(search_query, mode=tipo)
        
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                if tipo == "audio": 
                    await update.effective_chat.send_audio(audio=f)
                else: 
                    await update.effective_chat.send_video(video=f)
            
            os.remove(path)
            try:
                await wait_msg.delete()
            except:
                pass
        else:
            await wait_msg.edit_text("❌ Error al descargar.")
        return

    # 3. CASO: BÚSQUEDA
    wait_msg = None
    if not is_callback:
        wait_msg = await update.message.reply_text(f"🔍 Buscando <b>{search_query}</b>...", parse_mode='HTML')

    try:
        limit = 5
        search_limit = offset + limit + 1
        ydl_opts = {'quiet': True, 'extract_flat': True, 'force_generic_extractor': False}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_trigger = f"ytsearch{search_limit}:{search_query}"
            loop = asyncio.get_event_loop()
            search_result = await loop.run_in_executor(None, lambda: ydl.extract_info(search_trigger, download=False))
            all_entries = search_result.get('entries', [])
            entries = all_entries[offset:offset + limit]

        if not entries:
            if is_callback: await update.callback_query.answer("❌ Sin resultados.")
            elif wait_msg: await wait_msg.edit_text("❌ Sin resultados.")
            return

        keyboard = []
        for entry in entries:
            if not entry: continue
            v_id = entry.get('id')
            v_title = entry.get('title', 'Video')
            title_clean = (v_title[:45] + "..") if len(v_title) > 45 else v_title
            
            keyboard.append([InlineKeyboardButton(f"📺 {title_clean}", callback_data="ignore")])
            keyboard.append([
                InlineKeyboardButton("🎵 MP3", callback_data=f"yt_audio_{v_id}"),
                InlineKeyboardButton("🎥 Video", callback_data=f"yt_video_{v_id}")
            ])

        nav_buttons = []
        if offset > 0: 
            nav_buttons.append(InlineKeyboardButton("⬅️ Ant.", callback_data=f"yt_page_{offset-limit}"))
        if len(all_entries) > offset + limit: 
            nav_buttons.append(InlineKeyboardButton("Sig. ➡️", callback_data=f"yt_page_{offset+limit}"))
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

async def media_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: 
        from bot_main import user_manager 
    except: 
        user_manager = None

    query = update.callback_query
    data = query.data
    if data == "ignore": return await query.answer()
    
    if data.startswith("yt_page_"):
        await query.answer()
        return await handle_youtube_search(update, context, offset=int(data.split("_")[2]))

    await query.answer()
    try:
        parts = data.split("_")
        if len(parts) < 3: return
        mode = parts[1]
        video_id = parts[2]
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        tipo = "audio" if mode == "audio" else "video"
        
        if user_manager:
            user_manager.log(get_user_identifier(update), f"BOTON_{mode.upper()}", video_id)

        # Informamos al usuario
        await query.edit_message_text(f"⏳ Procesando <b>{mode.upper()}</b>...", parse_mode='HTML')
        
        path = await download_media(full_url, mode=tipo)
        
        if path and os.path.exists(path):
            # --- ENVÍO BLINDADO CON REINTENTOS ---
            for intento in range(2):
                try:
                    with open(path, 'rb') as f:
                        if tipo == "audio": 
                            await query.message.reply_audio(audio=f, connect_timeout=60, read_timeout=60)
                        else: 
                            await query.message.reply_video(video=f, connect_timeout=60, read_timeout=60)
                    break # Éxito: salimos del bucle de reintentos
                except Exception as e:
                    error_msg = str(e)
                    if ("Bad gateway" in error_msg or "Service failure" in error_msg) and intento == 0:
                        print(f"⚠️ Error de red ({error_msg}). Reintentando envío...")
                        await asyncio.sleep(2)
                        continue
                    # Si falla el segundo intento o es otro error, lanzamos la excepción para el bloque exterior
                    raise e
            
            # Limpieza tras éxito o fallos definitivos
            if os.path.exists(path): os.remove(path)
            
            # Borrado seguro del mensaje de "Procesando"
            try:
                await query.message.delete()
            except:
                pass
        else:
            await query.message.reply_text("❌ No se pudo descargar el video.")
            
    except Exception as e:
        # Aquí capturamos cualquier error definitivo (incluyendo los que raiseamos arriba)
        print(f"Error en callback: {e}")
        try:
            # Si el error es de Telegram porque el archivo es demasiado grande (Entity Too Large)
            if "Request Entity Too Large" in str(e):
                await query.message.reply_text("❌ El archivo es demasiado grande para Telegram (máx 50MB).")
            else:
                await query.message.reply_text("❌ Error al procesar la descarga.")
        except:
            pass
        finally:
            # Aseguramos que el archivo temporal se borre incluso si hubo un crash
            if 'path' in locals() and path and os.path.exists(path):
                os.remove(path)