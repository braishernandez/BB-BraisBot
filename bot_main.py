import os
import json
import shutil
import io
import re
import asyncio
import logging
import time
import tempfile

from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from user_manager import user_manager
from modules.libros import search_books, book_callback_handler
from modules.media import handle_youtube_search, media_callback_handler, download_media
from modules.updater import get_latest_biblioteca_bot
from modules.images import remove_background, prepare_sticker
from modules.pdf_parser import find_fillable_fields
from modules.pdf_editor import process_pdf_fields
from modules.audio import transcribir_y_traducir


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
    if user_id in whitelist: return True
    if username:
        whitelist_lower = [str(item).lower() for item in whitelist]
        if username in whitelist_lower: return True
    return False

def user_id_alt(update):
    return update.effective_user.id

# --- FUNCIONES DE APOYO PDF ---
async def finalizar_pdf(query, context):
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="upload_document")
    with open(context.user_data['pdf_path'], "rb") as f:
        pdf_bytes = f.read()
    final = process_pdf_fields(pdf_bytes, context.user_data['pdf_answers'], context.user_data['pdf_fields'], 
                               context.user_data['pdf_offset_x'], context.user_data['pdf_offset_y'])
    await context.bot.send_document(chat_id=query.message.chat_id, document=final, filename="Relleno.pdf")
    context.user_data.clear()
async def convert_pdf_to_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Intentamos sacar la ruta del context que guardamos en handle_pdf_upload
    pdf_path = context.user_data.get('pdf_path')

    if not pdf_path or not os.path.exists(pdf_path):
        await query.answer("❌ Error: Archivo no encontrado", show_alert=True)
        return await query.edit_message_text("❌ No encontré el archivo. Por favor, vuelve a subir el PDF.")

    await query.edit_message_text("⚙️ <b>Convirtiendo a Word...</b>\nEsto puede tardar unos segundos dependiendo del tamaño.", parse_mode='HTML')
    
    docx_path = pdf_path.replace(".pdf", ".docx")
    
    try:
        from pdf2docx import Converter
        # Procesar conversión
        cv = Converter(pdf_path)
        cv.convert(docx_path)
        cv.close()
        
        # Enviar el archivo
        await query.message.reply_document(
            document=open(docx_path, 'rb'),
            filename=os.path.basename(docx_path),
            caption="✅ Convertido correctamente."
        )
        await query.message.delete() # Borra el mensaje de "Convirtiendo..."
        
    except Exception as e:
        print(f"ERROR CONVERSIÓN: {e}")
        await query.message.reply_text(f"❌ Error técnico: {e}")
    finally:
        # Limpieza de archivos temporales
        if os.path.exists(docx_path): os.remove(docx_path)
        if os.path.exists(pdf_path): os.remove(pdf_path)
        context.user_data.pop('pdf_path', None)
        
        
# --- COMANDOS Y CALLBACKS ---
async def start(update: Update, context):
    if not is_authorized(update):
        return await update.message.reply_text("⛔ No estás autorizado.")
    user_name = update.effective_user.username or update.effective_user.first_name
    texto_bienvenida = (
        f"👋 Hola <b>@{user_name}</b>\n\n"
        "📹 <b>Media:</b> Descarga YouTube, TikTok, IG, X.\n"
        "📚 <b>Libros:</b> LibGen y biblioteca local.\n"
        "🖼️ <b>Imágenes:</b> Quita fondos y Stickers.\n"
        "📄 <b>PDFs:</b> Une, rellena o convierte a Word."
    )
    keyboard = [
        [InlineKeyboardButton("📚 Libros", callback_data="menu_books"), InlineKeyboardButton("🎬 Media", callback_data="menu_media")],
        [InlineKeyboardButton("🖼️ Imágenes", callback_data="menu_images"), InlineKeyboardButton("📄 PDFs", callback_data="menu_pdf")]
    ]
    await update.message.reply_text(texto_bienvenida, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def menu_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pdf_to_merge'] = []
    keyboard = [
        [InlineKeyboardButton("➕ Empezar a unir PDFs", callback_data="start_merging")],
        [InlineKeyboardButton("🔄 Convertir a Word", callback_data="start_conversion")]
    ]
    await query.edit_message_text("📂 <b>Herramientas PDF</b>\n\nElige una opción:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def start_merging(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['merging_active'] = True
    context.user_data['pdf_to_merge'] = []
    await query.edit_message_text("📥 <b>Modo Unión Activo</b>\nEnvíame los PDFs. Al terminar pulsa el botón.", 
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ¡Unir ahora!", callback_data="do_merge")]]), parse_mode='HTML')

async def unir_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    context.user_data['merging_active'] = True
    context.user_data['pdf_to_merge'] = []
    await update.message.reply_text("📥 Modo Unión Activo. Envíame los PDFs.")

async def do_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = update.callback_query is not None
    if is_callback: await update.callback_query.answer()
    files = context.user_data.get('pdf_to_merge', [])
    if len(files) < 2:
        return await update.effective_message.reply_text("❌ Necesito al menos 2 PDFs.")
    from modules.pdf_editor import merge_pdfs 
    output = f"downloads/union_{update.effective_user.id}.pdf"
    try:
        merge_pdfs(files, output)
        await update.effective_chat.send_document(document=open(output, 'rb'), filename="PDF_Unido.pdf")
        context.user_data['merging_active'] = False
        for f in files: os.remove(f)
    except Exception as e: await update.effective_message.reply_text(f"❌ Error: {e}")

async def handle_pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    doc = update.message.document
    
    # 1. Guardamos el archivo inmediatamente para tenerlo disponible
    pdf_path = f"downloads/temp_{update.effective_user.id}_{doc.file_name}"
    file = await doc.get_file()
    await file.download_to_drive(pdf_path)
    
    # 2. Guardamos la ruta en el contexto del usuario
    context.user_data['pdf_path'] = pdf_path

    # CASO ESPECIAL: Si ya estamos en "Modo Unión", seguimos añadiendo a la lista
    if context.user_data.get('merging_active'):
        context.user_data.setdefault('pdf_to_merge', []).append(pdf_path)
        count = len(context.user_data['pdf_to_merge'])
        return await update.message.reply_text(
            f"✅ Archivo {count} añadido a la lista de unión.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ¡Unir ahora!", callback_data="do_merge")]])
        )
    
    # CASO NORMAL: Preguntamos qué quiere hacer el usuario
    keyboard = [
        [
            InlineKeyboardButton("📝 Rellenar Campos", callback_data="option_fill"),
            InlineKeyboardButton("🔄 Convertir a Word", callback_data="pdf_to_word")
        ],
        [InlineKeyboardButton("❌ Cancelar", callback_data="menu_pdf")]
    ]
    
    await update.message.reply_text(
        f"📄 <b>Archivo recibido:</b> <code>{doc.file_name}</code>\n\n"
        "¿Qué deseas hacer con este documento?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
async def prepare_fill_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pdf_path = context.user_data.get('pdf_path')
    if not pdf_path or not os.path.exists(pdf_path):
        return await query.edit_message_text("❌ Error: No se encuentra el archivo. Reenvíalo.")

    await query.edit_message_text("🔍 Analizando estructura del formulario...")
    
    # Llamamos a tu lógica de siempre para buscar campos
    fields = find_fillable_fields(pdf_path)
    
    if not fields:
        return await query.edit_message_text("❌ Este PDF no parece tener campos editables.")

    context.user_data.update({
        'pdf_fields': fields, 
        'pdf_answers': [], 
        'pdf_step': 0, 
        'pdf_offset_x': 0, 
        'pdf_offset_y': 5
    })
    
    label = fields[0].get('label', 'Campo 1')
    await query.message.reply_text(f"✅ Detectados {len(fields)} campos.\n\n📝 <b>{label}:</b>", parse_mode='HTML')
    
    
async def handle_photo(update: Update, context):
    if not is_authorized(update): return
    msg = await update.message.reply_text("⏳ Procesando...")
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = bytes(await photo_file.download_as_bytearray()) 
    no_bg_bytes = remove_background(image_bytes)
    context.user_data['last_img'] = no_bg_bytes
    keyboard = [[InlineKeyboardButton("🖼 PNG", callback_data="img_png"), InlineKeyboardButton("✨ Sticker", callback_data="img_sticker")]]
    await msg.edit_text("✅ Listo:", reply_markup=InlineKeyboardMarkup(keyboard))

async def global_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_authorized(update): return
    
    # Si estamos rellenando un PDF, procesamos el texto
    if 'pdf_step' in context.user_data:
        text = update.message.text
        context.user_data['pdf_answers'].append(text)
        steps = len(context.user_data['pdf_answers'])
        fields = context.user_data['pdf_fields']
        
        if steps < len(fields):
            await update.message.reply_text(f"📝 <b>{fields[steps].get('label', f'Campo {steps+1}')}:</b>", parse_mode='HTML')
        else:
            await update.message.reply_text("✅ Datos listos.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Generar", callback_data="pdf_final")]]))
        return

    # IMPORTANTE: Aquí ya NO llamamos a handle_youtube_search. 
    # Ahora solo se activará con el comando /video.

async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    
    if not context.args:
        return await update.message.reply_text("❌ Uso: <code>/video nombre o enlace</code>", parse_mode='HTML')
    
    query = " ".join(context.args)
    
    # Ahora enviamos el texto directamente como 'query_override'
    from modules.media import handle_youtube_search
    await handle_youtube_search(update, context, query_override=query)
    
     
async def pdf_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "pdf_final": await finalizar_pdf(query, context)

async def image_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    img = context.user_data.get('last_img')
    if not img: return
    if query.data == "img_png":
        await context.bot.send_document(query.message.chat_id, document=io.BytesIO(img), filename="bg_removed.png")
    elif query.data == "img_sticker":
        await context.bot.send_sticker(query.message.chat_id, sticker=prepare_sticker(img))

async def menu_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "menu_books": await query.message.reply_text("📚 Usa /book [titulo]")
    elif query.data == "menu_media": await query.message.reply_text("🎵 Envía nombre o link")

async def autorizar(update: Update, context):
    if not user_manager.is_admin(update.effective_user.username): return
    if context.args:
        nuevo = context.args[0]
        user_manager.config.setdefault('whitelist', []).append(nuevo)
        user_manager._save()
        await update.message.reply_text(f"✅ {nuevo} autorizado.")

async def stats(update: Update, context):
    if not user_manager.is_admin(update.effective_user.username): return
    total_size = sum(f.stat().st_size for f in Path("downloads").glob('**/*') if f.is_file()) / (1024 * 1024)
    await update.message.reply_text(f"📊 Temporal: {total_size:.2f} MB")

async def error_handler(update, context):
    print(f"❌ Error: {context.error}")


# --- AUDIO / TRANSCRIPCIÓN ---
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja notas de voz y audios — cualquier usuario puede usar esto."""
    msg = update.message
    if not msg:
        return

    # Aceptar tanto voice (nota de voz) como audio (archivo de audio)
    file_obj = msg.voice or msg.audio
    if not file_obj:
        return

    # Límite 20MB
    if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
        await msg.reply_text("❌ Audio demasiado grande. Máximo 20MB.")
        return

    aviso = await msg.reply_text("🎙️ Transcribiendo audio... puede tardar un momento.")

    try:
        # Descargar audio
        tg_file = await file_obj.get_file()
        ext = '.ogg'
        if msg.audio and msg.audio.file_name:
            ext = os.path.splitext(msg.audio.file_name)[1] or '.mp3'
        tmp_path = tempfile.mktemp(suffix=ext)
        await tg_file.download_to_drive(tmp_path)

        # Transcribir y traducir
        resultado = transcribir_y_traducir(tmp_path, modelo='small')

        os.unlink(tmp_path)

        idioma_txt = resultado['idioma_nombre'].capitalize()
        texto_orig = resultado['texto_original']
        texto_trad = resultado['texto_traducido']

        if texto_trad and texto_trad != texto_orig:
            respuesta = (
                f"🎙️ <b>Transcripción</b> ({idioma_txt})\n"
                f"{texto_orig}\n\n"
                f"🌐 <b>Traducción al inglés</b>\n"
                f"{texto_trad}"
            )
        else:
            respuesta = (
                f"🎙️ <b>Transcripción</b> ({idioma_txt})\n"
                f"{texto_orig}"
            )

        await aviso.edit_text(respuesta, parse_mode='HTML')

    except Exception as e:
        await aviso.edit_text(f"❌ Error procesando el audio: {e}")


# --- MAIN ---
# --- MAIN ACTUALIZADO ---
def main():
    clean_downloads()
    app = Application.builder().token(user_manager.get_token()).build()
    
    # 1. Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unir", unir_command))
    app.add_handler(CommandHandler("listo", do_merge))
    app.add_handler(CommandHandler("book", search_books))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("autorizar", autorizar))
    app.add_handler(CommandHandler("video", video_command))

    # 2. Callbacks (ORDEN CORREGIDO: De lo más específico a lo más general)
    
    # Botones directos del menú PDF
    app.add_handler(CallbackQueryHandler(prepare_fill_pdf, pattern="^option_fill$"))
    app.add_handler(CallbackQueryHandler(convert_pdf_to_word, pattern="^pdf_to_word$"))
    app.add_handler(CallbackQueryHandler(convert_pdf_to_word, pattern="^start_conversion$"))
    
    # Menús generales
    app.add_handler(CallbackQueryHandler(menu_pdf, pattern="^menu_pdf$"))
    app.add_handler(CallbackQueryHandler(start_merging, pattern="^start_merging$"))
    app.add_handler(CallbackQueryHandler(do_merge, pattern="^do_merge$"))
    
    # Handlers por módulos (Regex)
    # MUY IMPORTANTE: Estos deben ir AL FINAL porque atrapan cualquier cosa que empiece por pdf_ o bk_
    app.add_handler(CallbackQueryHandler(pdf_callback_handler, pattern=r'^pdf_'))
    app.add_handler(CallbackQueryHandler(image_callback_handler, pattern=r'^img_'))
    app.add_handler(CallbackQueryHandler(book_callback_handler, pattern=r'^bk_'))
    app.add_handler(CallbackQueryHandler(media_callback_handler, pattern=r'^(yt_|music_)'))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern=r'^menu_'))
    
    # 3. Mensajes
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf_upload))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_handler))
    
    app.add_error_handler(error_handler)
    print("🚀 Bot iniciado correctamente.")
    app.run_polling()

if __name__ == '__main__':
    main()