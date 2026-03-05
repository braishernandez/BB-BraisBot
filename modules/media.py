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
    
    youtube_cookies = r"C:\BOT\www.youtube.com_cookies.txt"
    ig_cookies = r"C:\BOT\BB-BraisBot\instagram_cookies.txt"
    base_name = f"media_{int(asyncio.get_event_loop().time())}"
    temp_output = os.path.join("downloads", f"{base_name}.%(ext)s")
    
    try:
        # 1. RESOLUCIÓN DE REDIRECCIONES
        target_url = url.strip()
        if "facebook.com/share" in target_url:
            print(f"🔍 Resolviendo redirección de Meta...")
            cmd_resolve = ["curl", "-Ls", "-o", "NUL", "-w", "%{url_effective}", target_url]
            proc = await asyncio.create_subprocess_exec(*cmd_resolve, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            res = stdout.decode().strip()
            if res: target_url = res.split("?")[0]
            print(f"🎯 URL Destino: {target_url}")

        is_instagram = any(x in target_url for x in ["instagram.com", "ig.me"])
        is_facebook = "facebook.com" in target_url or "fb.watch" in target_url
        cookie_path = ig_cookies if (is_instagram or is_facebook) and os.path.exists(ig_cookies) else youtube_cookies

        # 2. INTENTO DE DESCARGA
        print(f"--- [INICIANDO DESCARGA: {target_url}] ---")
        
        async def run_dlp(use_cookies=True):
            args = [
                "yt-dlp", "--no-check-certificate",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "--merge-output-format", "mp4", "--output", temp_output
            ]
            if use_cookies and os.path.exists(cookie_path):
                args.extend(["--cookies", cookie_path])
            args.append(target_url)
            
            p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await p.communicate()
            return out, err

        stdout, stderr = await run_dlp(use_cookies=True)
        err_msg = stderr.decode()

        # 3. MANEJO DE ERRORES Y RETRY
        if "Cannot parse data" in err_msg:
            print("📢 Error de parseo detectado. Reintentando sin cookies (Guest Mode)...")
            stdout, stderr = await run_dlp(use_cookies=False)
            err_msg = stderr.decode()

        files = glob.glob(os.path.join("downloads", f"{base_name}.*"))

        # FALLBACK PARA INSTAGRAM (IMAGEN)
        if not files and is_instagram:
            print("📸 Buscando imagen...")
            img_args = ["yt-dlp", "--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg", "--output", temp_output, target_url]
            await (await asyncio.create_subprocess_exec(*img_args)).communicate()
            files = glob.glob(os.path.join("downloads", f"{base_name}.*"))

        if not files:
            # Aquí es donde el log te dirá la verdad
            if "Cannot parse data" in err_msg:
                print("❌ Meta ha bloqueado el extractor. Se requiere actualización de yt-dlp.")
            else:
                print(f"❌ Error del motor: {err_msg[:100]}")
            return None
        
        return max(files, key=os.path.getsize)

    except Exception as e:
        print(f"🔥 Error crítico: {e}")
        return None
        
async def handle_youtube_search(update: Update, context: ContextTypes.DEFAULT_TYPE, format_type=None, offset=0, query_override=None):
    try: from bot_main import user_manager
    except ImportError: user_manager = None

    is_callback = update.callback_query is not None
    if query_override: search_query = query_override
    elif is_callback:
        query_text = update.callback_query.message.text
        search_query = query_text.replace('🔍 Resultados para: ', '').split('\n')[0].strip()
    else:
        text = update.message.text
        search_query = re.sub(r'^/(mp3|video)\s*', '', text).strip()

    if not search_query: return
    is_url = search_query.startswith(('http://', 'https://'))

    # --- CASO: DESCARGA DIRECTA ---
    if not is_callback and is_url:
        cmd = update.message.text.split()[0].lower() if update.message.text else ""
        tipo = "audio" if (format_type == "mp3" or "/mp3" in cmd) else "video"
        
        u_name = get_user_identifier(update)
        chat = update.effective_chat
        label = "PRIVADO" if chat.type == "private" else f"GRUPO:{chat.title[:15]}"
        
        if user_manager: user_manager.log(u_name, f"DIRECT_{tipo.upper()}", search_query, origen=label)

        wait_msg = await update.message.reply_text(f"🚀 Procesando {tipo}...")
        path = await download_media(search_query, mode=tipo)
        
        if path and os.path.exists(path):
            ext = path.lower()
            with open(path, 'rb') as f:
                if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    await update.effective_chat.send_photo(photo=f, caption="📸 Imagen extraída del post.")
                elif tipo == "audio" or ext.endswith(('.mp3', '.m4a')):
                    await update.effective_chat.send_audio(audio=f)
                else:
                    await update.effective_chat.send_video(video=f)
            os.remove(path)
            try: await wait_msg.delete()
            except: pass
        else:
            await wait_msg.edit_text("❌ Error al descargar.")
        return

    # --- CASO: BÚSQUEDA ---
    wait_msg = None
    if not is_callback:
        wait_msg = await update.message.reply_text(f"🔍 Buscando <b>{search_query}</b>...", parse_mode='HTML')

    try:
        limit = 5
        search_limit = offset + limit + 1
        ydl_opts = {'quiet': True, 'extract_flat': True}
        
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
        if offset > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Ant.", callback_data=f"yt_page_{offset-limit}"))
        if len(all_entries) > offset + limit: nav_buttons.append(InlineKeyboardButton("Sig. ➡️", callback_data=f"yt_page_{offset+limit}"))
        if nav_buttons: keyboard.append(nav_buttons)

        text_display = f"🔍 Resultados para: <b>{search_query}</b>"
        if is_callback: await update.callback_query.edit_message_text(text_display, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        else:
            if wait_msg: await wait_msg.delete()
            await update.message.reply_text(text_display, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    except Exception as e:
        print(f"Error búsqueda: {e}")
        if wait_msg: await wait_msg.edit_text("❌ Error en la búsqueda.")

async def media_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        parts = data.split("_")
        if len(parts) < 3: return
        mode = parts[1]
        video_id = parts[2]
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        tipo = "audio" if mode == "audio" else "video"
        
        if user_manager: user_manager.log(get_user_identifier(update), f"BOTON_{mode.upper()}", video_id)

        await query.edit_message_text(f"⏳ Procesando <b>{mode.upper()}</b>...", parse_mode='HTML')
        path = await download_media(full_url, mode=tipo)
        
        if path and os.path.exists(path):
            ext = path.lower()
            for intento in range(2):
                try:
                    with open(path, 'rb') as f:
                        if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            await query.message.reply_photo(photo=f, caption="📸 Imagen extraída.")
                        elif tipo == "audio": 
                            await query.message.reply_audio(audio=f, connect_timeout=60, read_timeout=60)
                        else: 
                            await query.message.reply_video(video=f, connect_timeout=60, read_timeout=60)
                    break 
                except Exception as e:
                    if ("Bad gateway" in str(e)) and intento == 0:
                        await asyncio.sleep(2); continue
                    raise e
            
            if os.path.exists(path): os.remove(path)
            try: await query.message.delete()
            except: pass
        else:
            await query.message.reply_text("❌ No se pudo descargar el video.")
            
    except Exception as e:
        print(f"Error en callback: {e}")
        try:
            msg = "❌ El archivo es demasiado grande (máx 50MB)." if "Request Entity Too Large" in str(e) else "❌ Error al procesar."
            await query.message.reply_text(msg)
        except: pass
        finally:
            if 'path' in locals() and path and os.path.exists(path): os.remove(path)