import os
import json
import shutil
import io
import re
import asyncio
import logging

from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from user_manager import user_manager
from modules.libros import search_books, book_callback_handler
from modules.media import handle_youtube_search, media_callback_handler, download_media
from modules.updater import get_latest_biblioteca_bot
from modules.images import remove_background, prepare_sticker
from modules.pdf_parser import find_fillable_fields
from modules.pdf_editor import process_pdf_fields


# --- MANTENIMIENTO ---
def clean_downloads():
    folder = Path("downloads")
    if folder.exists():
        for f in folder.glob('*'):
            try:
                if f.is_file(): f.unlink()
                elif f.is_dir(): shutil.rmtree(f)
            except: pass
        user_manager.log("SYSTEM", "Carpeta downloads limpia")

# --- CONTROL DE ACCESO ROBUSTO ---
def is_authorized(update: Update):
    user = update.effective_user
    if not user: return False

    whitelist = user_manager.config.get('whitelist', [])
    user_id = str(user.id)
    username = user.username.lower() if user.username else None
    
    # Debug en consola para el administrador
    print(f"DEBUG AUTH: Intentando acceder -> ID: {user_id} | Username: @{username}")

    if user_id in whitelist: return True
    if username:
        whitelist_lower = [str(item).lower() for item in whitelist]
        if username in whitelist_lower: return True
            
    return False

def get_user_identifier(update: Update):
    user = update.effective_user
    return user.username if user.username else f"ID_{user.id}"

# --- COMANDOS PRINCIPALES ---
async def start(update: Update, context):
    if not is_authorized(update):
        user = update.effective_user
        user_manager.log("SISTEMA", f"ACCESO DENEGADO START: {user.full_name} ({user.id})")
        return await update.message.reply_text("⛔ No estás autorizado.")
    
    user_name = update.effective_user.username or update.effective_user.first_name
    user_manager.log(user_name, "Inició el bot")
    
    texto_bienvenida = (
        f"👋 Hola <b>@{user_name}</b>, ¡bienvenido a tu <b>BB-BraisBot</b>!\n\n"
        "Esta es tu navaja suiza de utilidades personales:\n\n"
        
        "📹 <b>Media & Redes Sociales</b>\n"
        "• YouTube (MP3/MP4) y enlaces de TikTok, IG, X.\n\n"
        
        "📚 <b>Gestión de Libros</b>\n"
        "• Búsqueda en LibGen y biblioteca local.\n\n"
        
        "🖼️ <b>Imágenes & Stickers</b>\n"
        "• Quita fondos y ajusta fotos a 512px.\n\n"
        
        "📄 <b>Utilidades PDF</b>\n"
        "• Rellenado inteligente de formularios PDF.\n\n"
        "✨ <i>Selecciona una opción o envía un archivo directamente:</i>"
    )

    # Teclado organizado en 2 columnas para que sea estético
    keyboard = [
        [
            InlineKeyboardButton("📚 Libros", callback_data="menu_books"),
            InlineKeyboardButton("🎬 Media", callback_data="menu_media")
        ],
        [
            InlineKeyboardButton("🖼️ Imágenes", callback_data="menu_images"),
            InlineKeyboardButton("📄 PDFs", callback_data="menu_pdf")
        ]
    ]

    await update.message.reply_text(
        texto_bienvenida,
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='HTML'
    )
async def error_handler(update: object, context) -> None:
    """Log de errores causados por actualizaciones."""
    # Evitamos logs gigantescos de errores de red temporales
    if "Server disconnected" in str(context.error) or "RemoteProtocolError" in str(context.error):
        print(f"⚠️ Reintentando conexión... (Error de red temporal)")
        return

    user_manager.log("ERROR", f"Causa: {context.error}")
    print(f"❌ Error crítico: {context.error}")
    
    # Si el error es manejable, avisamos al usuario
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("🤔 Hubo un pequeño problema técnico. Inténtalo de nuevo en un momento.")
# --- LÓGICA DE PDF ---
async def handle_pdf_upload(update: Update, context):
    if not update.message or not is_authorized(update): return

    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.pdf'): return

    msg = await update.message.reply_text("🔍 Analizando estructura del PDF...")
    try:
        pdf_file = await doc.get_file()
        path = f"downloads/temp_{update.effective_user.id}.pdf"
        await pdf_file.download_to_drive(path)
        
        fields = find_fillable_fields(path)
        if not fields:
            return await msg.edit_text("❌ No detecté campos de relleno en este PDF.")

        context.user_data.update({
            'pdf_path': path, 'pdf_fields': fields, 'pdf_answers': [],
            'pdf_step': 0, 'pdf_offset_x': 0, 'pdf_offset_y': 5
        })

        label = fields[0].get('label', 'Campo 1')
        await msg.edit_text(f"✅ Detectados {len(fields)} campos.\n\n📝 <b>{label}:</b>", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error interno: {e}")

# --- HANDLER DE TEXTO GLOBAL ---
async def global_text_handler(update: Update, context):
    # 1. IDENTIFICACIÓN ULTRA-SEGURA
    user = update.effective_user
    if not user: return

    # Si no tiene username, usamos su ID. Evitamos el error de 'NoneType'
    user_id = str(user.id)
    user_alias = f"@{user.username}" if user.username else f"ID:{user_id}"
    
    text = update.message.text if update.message.text else ""
    chat = update.effective_chat
    chat_title = chat.title[:30] if chat.title else "Privado"
    chat_label = "PRIVADO" if chat.type == "private" else f"GRUPO: {chat_title}"

    # 2. LOG ANTES DE CUALQUIER FILTRO (Para ver por qué falla)
    # Esto registrará TODO, incluso de usuarios no autorizados
    user_manager.log(user_alias, "INTENTO_TEXTO", text, origen=chat_label)

    # 3. CONTROL DE ACCESO
    if not is_authorized(update):
        if chat.type == "private":
            await update.message.reply_text("⛔ No estás autorizado.")
        return

    # --- A partir de aquí, el código para usuarios autorizados ---

    # 4. DETECTOR DE LINKS (IGNORAR SI NO HAY COMANDO)
    social_networks = ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "x.com"]
    if any(net in text.lower() for net in social_networks) and not text.startswith('/'):
        return 

    # 5. LÓGICA DE PDF
    user_data = context.user_data
    if 'pdf_step' in user_data:
        # (Tu lógica de PDF se mantiene igual...)
        user_data['pdf_answers'].append(text)
        fields = user_data['pdf_fields']
        next_step = len(user_data['pdf_answers'])
        if next_step < len(fields):
            user_data['pdf_step'] = next_step
            label = fields[next_step].get('label', f'Campo {next_step + 1}')
            await update.message.reply_text(f"📝 <b>{label}:</b>", parse_mode='HTML')
        else:
            keyboard = [[InlineKeyboardButton("🚀 Generar PDF ya", callback_data="pdf_final")]]
            await update.message.reply_text("✅ Datos listos.", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 6. MÚSICA
    if text.startswith('/'): return
    bot_obj = await context.bot.get_me()
    if chat.type == "private" or f"@{bot_obj.username}" in text:
        query = text.replace(f"@{bot_obj.username}", "").strip()
        if query:
            await handle_youtube_search(update, context)
# --- CALLBACKS PDF, IMÁGENES Y MENÚ ---
async def pdf_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "pdf_menu_ajuste":
        keyboard = [[InlineKeyboardButton("⬅️", callback_data="pdf_L"), InlineKeyboardButton("⬆️", callback_data="pdf_U"), 
                     InlineKeyboardButton("⬇️", callback_data="pdf_D"), InlineKeyboardButton("➡️", callback_data="pdf_R")],
                    [InlineKeyboardButton("✅ Listo, generar PDF", callback_data="pdf_final")]]
        await query.message.edit_text(f"📍 Ajuste: X={context.user_data['pdf_offset_x']} Y={context.user_data['pdf_offset_y']}", 
                                      reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "pdf_final":
        await finalizar_pdf(query, context)
    else:
        move = 2
        if query.data == "pdf_U": context.user_data['pdf_offset_y'] += move
        if query.data == "pdf_D": context.user_data['pdf_offset_y'] -= move
        if query.data == "pdf_L": context.user_data['pdf_offset_x'] -= move
        if query.data == "pdf_R": context.user_data['pdf_offset_x'] += move
        await query.message.edit_text(f"📍 Ajuste: X={context.user_data['pdf_offset_x']} Y={context.user_data['pdf_offset_y']}", 
                                      reply_markup=query.message.reply_markup)

async def finalizar_pdf(query, context):
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="upload_document")
    with open(context.user_data['pdf_path'], "rb") as f:
        pdf_bytes = f.read()
    final = process_pdf_fields(pdf_bytes, context.user_data['pdf_answers'], context.user_data['pdf_fields'], 
                               context.user_data['pdf_offset_x'], context.user_data['pdf_offset_y'])
    await context.bot.send_document(chat_id=query.message.chat_id, document=final, filename="Relleno.pdf")
    context.user_data.clear()

async def handle_photo(update: Update, context):
    if not is_authorized(update): return
    msg = await update.message.reply_text("⏳ Procesando imagen...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = bytes(await photo_file.download_as_bytearray()) 
        no_bg_bytes = remove_background(image_bytes)
        context.user_data['last_img'] = no_bg_bytes
        keyboard = [[InlineKeyboardButton("🖼 PNG", callback_data="img_png"), InlineKeyboardButton("✨ Sticker", callback_data="img_sticker")]]
        await msg.edit_text("✅ Fondo eliminado:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")

async def image_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    img_bytes = context.user_data.get('last_img')
    if not img_bytes: return
    if query.data == "img_png":
        bio = io.BytesIO(img_bytes)
        bio.name = "sin_fondo.png"
        await context.bot.send_document(query.message.chat_id, document=bio)
    elif query.data == "img_sticker":
        sticker_bio = prepare_sticker(img_bytes)
        await context.bot.send_sticker(query.message.chat_id, sticker=sticker_bio)

# --- ADMIN Y STATS ---
async def autorizar(update: Update, context):
    if not user_manager.is_admin(update.effective_user.username): return
    if not context.args: return
    nuevo = context.args[0]
    if 'whitelist' not in user_manager.config: user_manager.config['whitelist'] = []
    user_manager.config['whitelist'].append(nuevo)
    user_manager._save()
    await update.message.reply_text(f"✅ {nuevo} autorizado.")

async def stats(update: Update, context):
    if not user_manager.is_admin(update.effective_user.username): return
    down_dir = Path("downloads")
    total_size = sum(f.stat().st_size for f in down_dir.glob('**/*') if f.is_file()) / (1024 * 1024)
    await update.message.reply_text(f"📊 Temporal: {total_size:.2f} MB")

async def menu_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "menu_books": await query.message.reply_text("📚 Usa /book [titulo]")
    elif query.data == "menu_media": await query.message.reply_text("🎵 Envía nombre o link de YouTube")

# --- FUNCIÓN PRINCIPAL ---
def main():
    clean_downloads()
    token = user_manager.get_token()
    app = Application.builder().token(token).read_timeout(30).write_timeout(30).build()
    
    # Handlers de Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("book", search_books))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("autorizar", autorizar))    
    app.add_handler(CommandHandler("mp3", lambda u, c: handle_youtube_search(u, c, format_type="mp3")))
    app.add_handler(CommandHandler("video", lambda u, c: handle_youtube_search(u, c, format_type="video")))
    
    
    # Handlers de Archivos e Imágenes
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_upload))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)
    
    # Handlers de Callbacks (Botones)
    app.add_handler(CallbackQueryHandler(pdf_callback_handler, pattern=r'^pdf_'))
    app.add_handler(CallbackQueryHandler(image_callback_handler, pattern=r'^img_'))
    app.add_handler(CallbackQueryHandler(book_callback_handler, pattern=r'^bk_'))
    app.add_handler(CallbackQueryHandler(media_callback_handler, pattern=r'^(yt_|music_)'))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r'^menu_'))
    
    # Mensajes de texto (Último por prioridad)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_handler))
    
    print("🚀 Bot iniciado correctamente.")
    app.run_polling()

if __name__ == '__main__':
    while True:
        try:
            main()
        except Exception as e:
            print(f"🔄 El bot se cayó por un error crítico: {e}. Reiniciando en 5 segundos...")
            time.sleep(5)