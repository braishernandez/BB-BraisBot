import os
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from user_manager import user_manager

CACHE_FILE = Path("cache_libros.json")
DOWNLOAD_DIR = Path("downloads")
LIBGEN_MIRRORS = ["https://libgen.is", "https://libgen.rs", "https://libgen.li"]
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_to_cache(book_id, file_id):
    cache = load_cache()
    cache[str(book_id)] = file_id
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=4)

async def search_books(update, context):
    user_id = update.effective_user.username # O use_id si prefieres usar números
    
    # Bloqueo de seguridad
    if not user_manager.is_authorized(user_id):
        await update.message.reply_text("⛔ No estás autorizado para usar este bot.")
        user_manager.log(user_id, "ACCESO DENEGADO", origen="Seguridad")
        return
    user = update.effective_user.username
    query = ' '.join(context.args).lower()
    if not query: return await update.message.reply_text("❌ Uso: /book [título]")
    
    cache = load_cache()
    # BUSCAR EN CACHÉ POR NOMBRE (Para tus libros locales)
    for clave, file_id in cache.items():
        if query in clave:
            user_manager.log(user, "Libro local encontrado", clave)
            await update.message.reply_text(f"⚡ ¡Lo tengo en mi biblioteca local!")
            return await context.bot.send_document(update.message.chat_id, file_id)

    # Si no está en caché, sigue con la búsqueda normal en LibGen...
    
    user_manager.log(user, "Búsqueda libro", query)
    msg = await update.message.reply_text(f"🔍 Buscando <i>{query}</i>...", parse_mode='HTML')
    
    books = []
    for mirror in LIBGEN_MIRRORS:
        try:
            url = f"{mirror}/search.php?req={urllib.parse.quote(query)}&view=simple&column=def"
            r = requests.get(url, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', {'class': 'c'})
            if not table: continue
            
            for row in table.find_all('tr')[1:6]:
                cols = row.find_all('td')
                if len(cols) < 10: continue
                books.append({
                    'id': cols[0].text.strip(),
                    'authors': cols[1].text.strip()[:30],
                    'title': cols[2].text.strip()[:50],
                    'ext': cols[8].text.strip().lower(),
                    'mirror_page': cols[9].find('a')['href']
                })
            if books: break
        except: continue

    if not books:
        zlib_base = user_manager.get_zlib_url() or "https://z-lib.id"
        query_plus = query.replace(" ", "+")
        query_encoded = urllib.parse.quote(query)
        
        kb = [
            [InlineKeyboardButton("🤖 Buscar en Biblioteca Secreta", url=f"https://t.me/BibliotecaSecreta9889Bot?start={query_encoded}")],
            [InlineKeyboardButton("🌐 Buscar en Z-Library (Web)", url=f"{zlib_base}/s?q={query_plus}")]
        ]
        return await msg.edit_text("❌ Sin resultados directos. Prueba alternativas:", reply_markup=InlineKeyboardMarkup(kb))

    context.user_data['results'] = books
    kb = [[InlineKeyboardButton(f"📥 {b['title']} [{b['ext'].upper()}]", callback_data=f"bk_dl_{i}")] for i, b in enumerate(books)]
    await msg.edit_text("📚 Resultados en LibGen:", reply_markup=InlineKeyboardMarkup(kb))

# ESTA ES LA FUNCIÓN QUE FALTABA
async def book_callback_handler(update, context):
    query = update.callback_query
    user = query.from_user.username
    await query.answer()
    
    idx = int(query.data.split('_')[2])
    book = context.user_data['results'][idx]
    
    cache = load_cache()
    if str(book['id']) in cache:
        user_manager.log(user, "Libro desde Caché", book['title'])
        return await context.bot.send_document(query.message.chat_id, cache[str(book['id'])])

    status = await query.message.reply_text(f"⏳ Descargando: {book['title']}...")
    try:
        # Lógica de descarga simplificada para el ejemplo
        # (Aquí iría tu lógica de requests.get al mirror que ya tienes)
        pass 
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")