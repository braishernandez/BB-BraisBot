# -*- coding: utf-8 -*-
import os
import io
import re
import html
import shutil
import asyncio
import logging
import tempfile
import warnings
import mysql.connector

from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatType
from telegram.ext import (Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, TypeHandler, filters)
from telegram.error import NetworkError, TimedOut, BadRequest
from user_manager import user_manager

# Suprimir warning cosmético de PTB sobre per_message
warnings.filterwarnings('ignore', message='.*per_message=False.*')

# ── Módulos originales ────────────────────────────────────────────────────────
from modules.libros   import search_books, book_callback_handler
from modules.media    import handle_youtube_search, media_callback_handler, media_offer_callback_handler, download_media
from modules.updater  import get_latest_biblioteca_bot
from modules.images   import remove_background, prepare_sticker, bg_removal_ratio
from modules.pdf_parser import find_fillable_fields
from modules.pdf_editor import process_pdf_fields
from modules.wordle   import wordle_command, wranking_command, wordle_texto

# ── Módulos de transporte / servicios públicos (públicos) ────────────────────
from modules.titsa    import get_handlers as titsa_handlers, \
                             setup_secret as titsa_secret, \
                             get_location_handler as titsa_location_handler, \
                             get_text_handler as titsa_text_handler
from modules.tranvia  import get_handlers as tranvia_handlers, \
                             setup_secret as tranvia_secret, \
                             get_location_handler as tranvia_location_handler
from modules.gas      import get_handlers as gas_handlers, \
                             setup_secret as gas_secret, \
                             get_location_handler as gas_location_handler
from modules.farmacia import get_handlers as farmacia_handlers, \
                             setup_secret as farmacia_secret, \
                             get_location_handler as farmacia_location_handler
from modules.camaras  import setup_secret as camaras_secret
from modules.vuelo    import setup_secret as vuelo_secret
from modules.tiempo   import get_handlers as tiempo_handlers
from modules.tv       import get_handlers as tv_handlers
from modules.vuelo    import get_handlers as vuelo_handlers

# ── Módulos de alertas (públicos) ────────────────────────────────────────────
from modules.camaras    import get_handlers as camaras_handlers
from modules.despertador import get_handlers as despertador_handlers
from modules.divisas    import get_handlers as divisas_handlers
from modules.agro       import get_handlers as agro_handlers

# ── Módulos de utilidad (públicos) ───────────────────────────────────────────
from modules.verificador import get_handlers as verificador_handlers, \
                                get_offer_handlers as verificador_offer_handlers

# ── Módulos con auth propia (privados por BD/OTP) ────────────────────────────
from modules.lista_compra import get_handlers as lista_handlers
from modules.fichaje      import get_handlers as fichaje_handlers

# ── Módulos con setup() ──────────────────────────────────────────────────────
from modules.bingo  import setup as bingo_setup
from modules.sala   import setup as sala_setup
from modules.miau   import setup as miau_setup
from modules.enviomagico import setup as enviomagico_setup
from modules.crypto_telegram import setup as crypto_setup, setup_secret as crypto_secret
from modules.tablon import register as tablon_setup, setup_secret as tablon_secret

from modules.veoveo import get_handlers as veoveo_handlers
from modules.arrejuntados import setup as arrejuntados_setup
from modules.papanoel import setup as papanoel_setup
from modules.leer  import cmd_leer, leer_callback, leer_document_handler, leer_trigger_callback
from modules.teresitas import ter_handlers
from modules.bhid_login import setup as bhid_login_setup
from modules.trivial import setup as trivial_setup
from modules.tutor import setup as tutor_setup
from modules.amigoinvisible import setup as amigoinvisible_setup
from modules.pequelab import setup as pequelab_setup
from modules.bh_voz import setup as bh_voz_setup
from modules.turnos import setup as turnos_setup

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

esc = html.escape
DOWNLOADS = Path("downloads")
MAX_MSG = 4000          # Telegram corta en 4096; dejamos margen para el HTML


def _who(update: Update) -> str:
    u = update.effective_user
    if not u: return "?"
    name = f"@{u.username}" if u.username else u.first_name or str(u.id)
    return f"{name} ({u.id})"

def log_in(update: Update, what: str):
    logger.info(f"◀  {_who(update)} → {what}")

def log_out(who: str, what: str):
    logger.info(f"▶  BOT → {who} | {what}")

def log_ext(source: str, detail: str):
    logger.info(f"🌐  [{source}] {detail}")


# ══════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO DE COMANDOS — única fuente para el menú de /start, /comandos y el
#  menú «/» de Telegram. Al añadir un comando nuevo, se añade AQUÍ y sale en
#  los tres sitios. Al arrancar, el bot avisa en consola de los comandos
#  registrados que no están aquí y de los que están aquí pero no existen.
#
#  Cada comando: (nombres, argumentos, descripción). El primer nombre es el
#  principal (el que sale en el menú «/»); los demás son alias.
#  Fuera del catálogo a propósito: crypto (solo Brais), facturación/conta y admin.
# ══════════════════════════════════════════════════════════════════════════════
GENERAL = [
    (("start",),                     "", "Menú principal con todas las categorías"),
    (("comandos", "ayuda", "help"),  "", "Lista completa de comandos"),
]

CATALOGO = [
    ("menu_transport", "🚌 Transporte", [
        (("titsa", "guagua"),         "", "Guaguas TITSA: próximas paradas y planificador de rutas"),
        (("tranvia", "tram"),         "", "Tranvía de Tenerife: paradas y tiempos en tiempo real"),
        (("vuelo",),                  "", "Estado de un vuelo por número"),
        (("gas", "gasolineras"),      "", "Gasolineras más baratas cerca"),
        (("farmacia", "farmacias"),   "", "Farmacias de guardia cercanas"),
        (("teresitas",),              "", "Plazas libres en los aparcamientos de Las Teresitas"),
        (("tiempo",),                 "", "Meteorología por ubicación o nombre de lugar"),
    ], []),
    ("menu_alertas", "🔔 Alertas y avisos", [
        (("camalerta",),              "", "Alerta de tráfico por cámara (atasco, lluvia, niebla)"),
        (("micalertas",),             "", "Ver tus alertas de tráfico"),
        (("borraralerta",),           "", "Borrar una alerta de tráfico"),
        (("despertador",),            "", "Despertador con foto de tráfico y briefing del día"),
        (("misalarmas",),             "", "Ver tus despertadores"),
        (("divisaalerta",),           "", "Alerta cuando una divisa cruce tu umbral"),
        (("misalertas",),             "", "Ver y gestionar tus alertas de divisas"),
        (("agroalerta",),             "", "Alerta de precios agrícolas por cultivo y comunidad"),
        (("misagroalertas",),         "", "Ver tus alertas agrícolas"),
        (("borraragroalerta",),       "", "Borrar una alerta agrícola"),
    ], []),
    ("menu_juegos", "🎮 Juegos", [
        (("trivial",),                "[código]", "Trivial para el grupo con ranking; con el código de una sala de la web, jugáis esa sala (/trivial parar para pararlo)"),
        (("wordle",),                 "", "Wordle canario: la palabra canaria del día"),
        (("wranking",),               "", "Ranking del Wordle de hoy"),
        (("sala",),                   "", "Sala de juegos multijugador"),
        (("salaavisos",),             "", "Avisos de la sala de juegos"),
        (("veoveo",),                 "", "Veo Veo: crea una sala con una foto"),
        (("adivinar",),               "", "Veo Veo: salas abiertas para jugar"),
        (("miau",),                   "", "MiauCipher: mensajes secretos en idioma animal"),
        (("bingo",),                  "", "Tu balance del Bingo de la web"),
        (("experimento", "pequelab", "laboratorio"), "[edad]", "PequeLab: un experimento al azar para hacer en casa con los peques"),
    ], []),
    ("menu_media", "📹 Media", [
        (("video",),                  "[nombre o enlace]", "Busca y descarga vídeos de YouTube"),
        (("music",),                  "[canción]", "Busca y descarga música en MP3"),
        (("social",),                 "[url]", "Descarga de TikTok, Instagram, X y otras redes"),
        (("tv",),                     "", "TV y radio en directo de todo el mundo"),
        (("book",),                   "[título]", "Busca libros"),
        (("leer",),                   "", "Convierte un libro (PDF, EPUB, DOCX, TXT) a MP3"),
    ], ["🎙️ <i>Envía un audio o nota de voz para transcribirlo (y traducirlo)</i>",
        "🐾 <i>Si es un audio de MiauCipher, te lo descifro</i>"]),
    ("menu_servicios", "🌍 Servicios", [
        (("verificar",),              "", "Verifica noticias, imágenes, vídeos y enlaces con IA"),
        (("lista",),                  "", "Lista de la compra inteligente"),
        (("anadir",),                 "[productos]", "Añadir productos a la lista"),
        (("comprado",),               "[producto]", "Marcar un producto como comprado"),
        (("limpiar",),                "", "Vaciar la lista de la compra"),
        (("fichar",),                 "", "Control de fichaje (entrada/salida y bajas)"),
        (("tutor",),                  "", "Tutor de estudio: lo que te toca hoy, marcar sesiones y la nota del examen"),
        (("amigoinvisible",),         "[código]", "Amigo invisible: tus papeletas; en un grupo, con el código del panel, lo vincula"),
        (("turnos", "turno"),         "", "Turnos: tus números en cola y, si atiendes en un negocio, controlar la cola"),
        (("enviomagico",),            "", "Tus envíos de archivos activos"),
        (("tablon",),                 "", "Tablón de senderistas"),
        (("zonas",),                  "", "Tablón: zonas de senderismo"),
        (("publicar",),               "", "Tablón: publicar un aviso o mensaje"),
        (("michatid", "id"),          "", "Tu Chat ID de Telegram"),
    ], []),
    ("menu_utilidades", "🛠️ Utilidades", [
        (("papanoeliza",),            "", "🎅 Papanoelizador: gorros, cuernos de reno, duendes y texto en tus fotos"),
        (("arrejuntados",),           "", "Junta a dos personas en una foto, o añade a quien falta en una de grupo"),
        (("unir",),                   "", "Unir varios PDFs (envíalos y termina con /listo)"),
        (("listo",),                  "", "Terminar la unión de PDFs"),
    ], ["📄 <i>Envía un PDF</i> para rellenarlo o convertirlo a Word",
        "🖼️ <i>Envía una foto</i> para quitarle el fondo o hacer un sticker"]),
]

# Registrados pero que no deben salir en ningún menú (no generan aviso al arrancar).
COMANDOS_OCULTOS = {"stats", "autorizar", "cancelar", "cancel"}


def _linea_cmd(nombres, args, desc) -> str:
    cmds = " · ".join(f"/{n}" for n in nombres)
    if args:
        cmds += f" {esc(args)}"
    return f"{cmds} — {esc(desc)}"


def _texto_categoria(titulo: str, items, notas) -> str:
    lineas = [f"<b>{titulo}</b>", ""] + [_linea_cmd(*i) for i in items]
    if notas:
        lineas += [""] + list(notas)
    return "\n".join(lineas)


def _bloques_todos() -> list[str]:
    bloques = [_texto_categoria("📋 General", GENERAL, [])]
    bloques += [_texto_categoria(t, items, notas) for _, t, items, notas in CATALOGO]
    return bloques


def _trozos(bloques: list[str], limite: int = MAX_MSG) -> list[str]:
    """Junta bloques en mensajes de menos de `limite` caracteres."""
    out, actual = [], ""
    for b in bloques:
        if actual and len(actual) + len(b) + 2 > limite:
            out.append(actual)
            actual = b
        else:
            actual = f"{actual}\n\n{b}" if actual else b
    if actual:
        out.append(actual)
    return out


def _todos_los_nombres() -> set[str]:
    return {n for nombres, _, _ in GENERAL + [i for c in CATALOGO for i in c[2]] for n in nombres}


def _comandos_menu_slash() -> list[BotCommand]:
    vistos, out = set(), []
    for nombres, _, desc in GENERAL + [i for c in CATALOGO for i in c[2]]:
        n = nombres[0]
        if n not in vistos and re.fullmatch(r"[a-z0-9_]{1,32}", n):
            vistos.add(n)
            out.append(BotCommand(n, desc[:256]))
    return out[:100]     # límite de Telegram


def _teclado_inicio() -> InlineKeyboardMarkup:
    botones = [InlineKeyboardButton(t, callback_data=cb) for cb, t, _, _ in CATALOGO]
    botones.append(InlineKeyboardButton("📄 PDFs", callback_data="menu_pdf"))
    filas = [botones[i:i + 2] for i in range(0, len(botones), 2)]
    filas.append([InlineKeyboardButton("📋 Todos los comandos", callback_data="menu_todos")])
    return InlineKeyboardMarkup(filas)


def _saludo(user) -> str:
    nombre = esc(user.first_name or user.username or "")
    return f"👋 Hola <b>{nombre}</b>\n\nElige una categoría para ver los comandos disponibles:"


# --- CANALES: el bot no contesta NUNCA en canales ---
async def ignorar_canales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grupo -100: corta cualquier update de un canal (publicaciones, ediciones, botones…)
    antes de que llegue a ningún otro manejador."""
    chat = update.effective_chat
    if chat and chat.type == ChatType.CHANNEL:
        raise ApplicationHandlerStop


# --- MANTENIMIENTO ---
def clean_downloads():
    DOWNLOADS.mkdir(exist_ok=True)
    for f in DOWNLOADS.glob('*'):
        try:
            if f.is_file(): f.unlink()
            elif f.is_dir(): shutil.rmtree(f)
        except Exception:
            pass
    user_manager.log("SYSTEM", "Carpeta downloads limpia")


def _borrar(*rutas):
    for r in rutas:
        try:
            if r and os.path.exists(r): os.remove(r)
        except OSError:
            pass


# --- FUNCIONES DE APOYO PDF ---
PDF_KEYS = ('pdf_path', 'pdf_fields', 'pdf_answers', 'pdf_step', 'pdf_offset_x', 'pdf_offset_y')

def _limpiar_pdf(context):
    """Borra solo el estado del PDF (antes se hacía user_data.clear() y se perdía todo lo demás)."""
    _borrar(context.user_data.get('pdf_path'))
    for k in PDF_KEYS:
        context.user_data.pop(k, None)

async def finalizar_pdf(query, context):
    if 'pdf_fields' not in context.user_data or not os.path.exists(context.user_data.get('pdf_path', '')):
        return await query.message.reply_text("❌ Se ha perdido el PDF. Vuelve a enviarlo.")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="upload_document")
    with open(context.user_data['pdf_path'], "rb") as f:
        pdf_bytes = f.read()
    ud = context.user_data
    final = await asyncio.to_thread(process_pdf_fields, pdf_bytes, ud['pdf_answers'], ud['pdf_fields'],
                                    ud['pdf_offset_x'], ud['pdf_offset_y'])
    await context.bot.send_document(chat_id=query.message.chat_id, document=final, filename="Relleno.pdf")
    _limpiar_pdf(context)

def _pdf_a_word(pdf_path: str, docx_path: str):
    from pdf2docx import Converter
    cv = Converter(pdf_path)
    try:
        cv.convert(docx_path)
    finally:
        cv.close()

async def convert_pdf_to_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pdf_path = context.user_data.get('pdf_path')
    if not pdf_path or not os.path.exists(pdf_path):
        await query.answer("❌ Error: Archivo no encontrado", show_alert=True)
        return await query.edit_message_text("❌ No encontré el archivo. Por favor, vuelve a subir el PDF.")
    await query.answer()
    await query.edit_message_text("⚙️ <b>Convirtiendo a Word...</b>\nEsto puede tardar unos segundos.", parse_mode='HTML')
    docx_path = pdf_path[:-4] + ".docx" if pdf_path.lower().endswith(".pdf") else pdf_path + ".docx"
    try:
        await asyncio.to_thread(_pdf_a_word, pdf_path, docx_path)
        with open(docx_path, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(docx_path),
                                               caption="✅ Convertido correctamente.")
        await query.message.delete()
    except Exception as e:
        logger.error(f"❌ PDF → Word: {e}", exc_info=True)
        await query.message.reply_text(f"❌ Error técnico: {e}")
    finally:
        _borrar(docx_path, pdf_path)
        context.user_data.pop('pdf_path', None)


# --- COMANDOS PÚBLICOS ---
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/id y /michatid (único para todo el bot; antes estaba repetido en bingo.py y clases.py)."""
    uid = update.effective_user.id
    await update.effective_message.reply_text(
        f"🆔 Tu Chat ID de Telegram es:\n\n<code>{uid}</code>\n\n"
        "Cópialo donde te lo pidan (por ejemplo, en Pareja Astral). "
        "Para el resto de herramientas de braishernandez.com basta con el botón "
        "<b>Iniciar sesión con Telegram</b>.",
        parse_mode='HTML'
    )

async def start(update: Update, context):
    log_in(update, "/start")
    # Enlaces antiguos t.me/BraishBot?start=michatid
    if context.args and context.args[0] == 'michatid':
        return await id_command(update, context)
    await update.effective_message.reply_text(_saludo(update.effective_user),
                                              reply_markup=_teclado_inicio(), parse_mode='HTML')
    log_out(str(update.effective_user.id), "Menú principal")

async def comandos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/comandos · /ayuda · /help — todos los comandos de una vez."""
    log_in(update, "/comandos")
    for trozo in _trozos(_bloques_todos()):
        await update.effective_message.reply_text(trozo, parse_mode='HTML', disable_web_page_preview=True)

async def menu_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['pdf_to_merge'] = []
    keyboard = [
        [InlineKeyboardButton("➕ Unir PDFs", callback_data="start_merging")],
        [InlineKeyboardButton("🔄 Convertir a Word", callback_data="start_conversion")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu_inicio")],
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
    _borrar(*context.user_data.get('pdf_to_merge', []))
    context.user_data['merging_active'] = True
    context.user_data['pdf_to_merge'] = []
    await update.message.reply_text("📥 Modo Unión Activo. Envíame los PDFs y termina con /listo.")

async def do_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    if not context.user_data.get('merging_active'):
        return await update.effective_message.reply_text("ℹ️ No hay ninguna unión en marcha. Empieza con /unir")
    files = context.user_data.get('pdf_to_merge', [])
    if len(files) < 2:
        return await update.effective_message.reply_text("❌ Necesito al menos 2 PDFs.")
    from modules.pdf_editor import merge_pdfs
    output = str(DOWNLOADS / f"union_{update.effective_user.id}.pdf")
    try:
        await asyncio.to_thread(merge_pdfs, files, output)
        with open(output, 'rb') as f:
            await update.effective_chat.send_document(document=f, filename="PDF_Unido.pdf")
        context.user_data['merging_active'] = False
        context.user_data['pdf_to_merge'] = []
        _borrar(*files)
    except Exception as e:
        logger.error(f"❌ Unir PDFs: {e}", exc_info=True)
        await update.effective_message.reply_text(f"❌ Error: {e}")
    finally:
        _borrar(output)

async def handle_pdf_or_leer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Si hay un estado leer activo, el PDF va al conversor TTS; si no, al flujo normal de PDF."""
    from modules.leer import leer_state
    chat_id = update.effective_chat.id
    if chat_id in leer_state and 'voice' in leer_state[chat_id]:
        await leer_document_handler(update, context)
    else:
        await handle_pdf_upload(update, context)

async def handle_pdf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    log_in(update, f"PDF: {doc.file_name}")
    # Nombre limpio: el de Telegram puede traer espacios raros, barras o venir vacío
    limpio = re.sub(r'[^\w.\-]+', '_', doc.file_name or 'documento.pdf')[-80:]
    pdf_path = str(DOWNLOADS / f"temp_{update.effective_user.id}_{doc.file_unique_id}_{limpio}")
    file = await doc.get_file()
    await file.download_to_drive(pdf_path)
    if context.user_data.get('merging_active'):
        context.user_data.setdefault('pdf_to_merge', []).append(pdf_path)
        count = len(context.user_data['pdf_to_merge'])
        return await update.message.reply_text(
            f"✅ Archivo {count} añadido a la lista de unión.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ¡Unir ahora!", callback_data="do_merge")]])
        )
    # Un PDF nuevo sustituye al anterior (y a un relleno a medias)
    _limpiar_pdf(context)
    context.user_data['pdf_path'] = pdf_path
    keyboard = [
        [InlineKeyboardButton("📝 Rellenar Campos", callback_data="option_fill"),
         InlineKeyboardButton("🔄 Convertir a Word", callback_data="pdf_to_word")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="menu_pdf")]
    ]
    await update.message.reply_text(
        f"📄 <b>Archivo recibido:</b> <code>{esc(doc.file_name or 'documento.pdf')}</code>\n\n¿Qué deseas hacer con este documento?",
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
    fields = await asyncio.to_thread(find_fillable_fields, pdf_path)
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
    await query.message.reply_text(f"✅ Detectados {len(fields)} campos.\n\n📝 <b>{esc(str(label))}:</b>", parse_mode='HTML')

async def handle_photo(update: Update, context):
    log_in(update, "Foto → quitar fondo")
    msg = await update.message.reply_text("⏳ Procesando...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = bytes(await photo_file.download_as_bytearray())
        # rembg es CPU pura: en un hilo para no congelar el bot entero mientras tanto
        no_bg_bytes = await asyncio.to_thread(remove_background, image_bytes)
        ratio = await asyncio.to_thread(bg_removal_ratio, no_bg_bytes)
    except Exception as e:
        logger.error(f"❌ Quitar fondo: {e}", exc_info=True)
        return await msg.edit_text("❌ No he podido procesar la foto. Prueba con otra.")
    log_ext("rembg", f"Fondo eliminado para {_who(update)}")

    if ratio < 0.15:
        # rembg no encontró un sujeto claro (memes, capturas, ilustraciones con
        # varios elementos) y se dejó casi toda la imagen fuera -> usamos el original
        log_ext("rembg", f"Cobertura muy baja ({ratio:.0%}) para {_who(update)} — uso imagen original")
        context.user_data['last_img'] = image_bytes
        texto_listo = "⚠️ No he podido separar bien el fondo en esta imagen (parece tener varios elementos). Uso la imagen original.\n\n✅ Listo:"
    else:
        context.user_data['last_img'] = no_bg_bytes
        texto_listo = "✅ Listo:"

    keyboard = [[InlineKeyboardButton("🖼 PNG", callback_data="img_png"),
                 InlineKeyboardButton("✨ Sticker", callback_data="img_sticker")]]
    await msg.edit_text(texto_listo, reply_markup=InlineKeyboardMarkup(keyboard))

async def global_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grupo 1 (antes estaba en el 0 detrás de wordle_texto y no se ejecutaba NUNCA:
    en PTB solo corre el primer handler que encaja de cada grupo)."""
    if not update.message or not update.message.text: return
    if 'pdf_step' not in context.user_data:
        log_in(update, f"Texto: {update.message.text[:60]}")
        return
    fields = context.user_data.get('pdf_fields') or []
    answers = context.user_data.setdefault('pdf_answers', [])
    if len(answers) >= len(fields):
        return      # ya están todos; falta pulsar «Generar»
    answers.append(update.message.text)
    steps = len(answers)
    if steps < len(fields):
        label = fields[steps].get('label', f'Campo {steps+1}')
        await update.message.reply_text(f"📝 <b>{esc(str(label))}:</b>", parse_mode='HTML')
    else:
        await update.message.reply_text("✅ Datos listos.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Generar", callback_data="pdf_final")]]))

async def social_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Uso: <code>/social [url]</code>", parse_mode='HTML')
    url = context.args[0]
    log_in(update, f"/social {url[:80]}")
    await handle_youtube_search(update, context, query_override=url)

async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Uso: <code>/video nombre o enlace</code>", parse_mode='HTML')
    query = " ".join(context.args)
    log_in(update, f"/video {query[:60]}")
    await handle_youtube_search(update, context, query_override=query)

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("❌ Uso: <code>/music nombre canción</code>", parse_mode='HTML')
    query = " ".join(context.args)
    log_in(update, f"/music {query[:60]}")
    await handle_youtube_search(update, context, format_type="mp3", query_override=query)

async def pdf_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "pdf_final": await finalizar_pdf(query, context)

async def image_callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    img = context.user_data.get('last_img')
    if not img:
        log_in(update, "img_ callback → sin imagen en user_data")
        await query.message.reply_text("⚠️ No encuentro la imagen, envíala de nuevo.")
        return
    try:
        if query.data == "img_png":
            log_in(update, "Botón PNG")
            await context.bot.send_document(query.message.chat_id, document=io.BytesIO(img), filename="bg_removed.png")
        elif query.data == "img_sticker":
            log_in(update, "Botón Sticker")
            await context.bot.send_sticker(query.message.chat_id, sticker=prepare_sticker(img))
    except Exception as e:
        logger.error(f"❌ Error en image_callback_handler: {e}", exc_info=True)
        await query.message.reply_text(f"❌ Error: {e}")

async def menu_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    volver = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu_inicio")]])

    if query.data == "menu_inicio":
        return await query.edit_message_text(_saludo(query.from_user), reply_markup=_teclado_inicio(), parse_mode='HTML')

    if query.data == "menu_todos":
        for trozo in _trozos(_bloques_todos()):
            await context.bot.send_message(query.message.chat_id, trozo, parse_mode='HTML',
                                           disable_web_page_preview=True)
        return

    cat = next((c for c in CATALOGO if c[0] == query.data), None)
    if cat:
        _, titulo, items, notas = cat
        await query.edit_message_text(_texto_categoria(titulo, items, notas), reply_markup=volver, parse_mode='HTML')


# --- COMANDOS ADMIN ---
async def autorizar(update: Update, context):
    if not user_manager.is_admin(update.effective_user): return
    if context.args:
        nuevo = user_manager.autorizar(context.args[0])
        await update.message.reply_text(f"✅ {nuevo} autorizado.")
    else:
        await update.message.reply_text("Uso: /autorizar @usuario  (o su ID numérico si no tiene @)")

async def stats(update: Update, context):
    if not user_manager.is_admin(update.effective_user): return
    total_size = sum(f.stat().st_size for f in DOWNLOADS.glob('**/*') if f.is_file()) / (1024 * 1024)
    await update.message.reply_text(f"📊 Temporal: {total_size:.2f} MB")

async def error_handler(update, context):
    err = context.error
    # Cortes de red transitorios: la librería ya reintenta sola
    if isinstance(err, (NetworkError, TimedOut)) and not isinstance(err, BadRequest):
        logger.warning(f"🌐 Corte de red con Telegram ({type(err).__name__}) — reintentando")
        return
        
    donde = ""
    if isinstance(update, Update):
        chat = update.effective_chat
        donde = f" [{_who(update)} en {chat.type if chat else '?'} {chat.id if chat else ''}]"
    logger.error(f"❌ Error{donde}: {context.error}", exc_info=context.error)


# --- AUDIO / TRANSCRIPCIÓN ---
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    file_obj = msg.voice or msg.audio
    if not file_obj: return
    log_in(update, f"Audio ({(file_obj.file_size or 0)//1024} KB)")
    if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
        await msg.reply_text("❌ Audio demasiado grande. Máximo 20MB.")
        return
    aviso = await msg.reply_text("🎙️ Transcribiendo audio... puede tardar un momento.")
    ext = '.ogg'
    if msg.audio and msg.audio.file_name:
        ext = os.path.splitext(msg.audio.file_name)[1] or '.mp3'
    fd, tmp_path = tempfile.mkstemp(suffix=ext)      # mktemp es inseguro y está obsoleto
    os.close(fd)
    try:
        from modules.audio import transcribir, traducir
        tg_file = await file_obj.get_file()
        await tg_file.download_to_drive(tmp_path)
        # Whisper tarda: en un hilo, para que el resto del bot siga contestando mientras
        resultado = await asyncio.to_thread(transcribir, tmp_path, modelo='small')
        idioma = resultado['idioma']
        idioma_txt = resultado['idioma_nombre'].capitalize()
        texto = resultado['texto']
        log_ext("Whisper", f"Transcripción OK — {idioma_txt}, {resultado.get('duracion_seg',0):.0f}s audio")
        texto_trad = None
        if idioma not in ('es', 'gl', 'ca'):
            texto_trad = await asyncio.to_thread(traducir, tmp_path, modelo='small')
        context.user_data['ultimo_texto'] = texto
        context.user_data['ultimo_idioma'] = idioma_txt
        user = update.effective_user
        username = user.username or user.first_name or str(user.id)
        dur_min = resultado.get('duracion_seg', 0) / 60
        t_proc  = resultado.get('tiempo_proceso', 0)
        user_manager.log(username, "TRANSCRIPCIÓN", f"Audio {dur_min:.1f} min | Procesado en {t_proc:.1f}s | Idioma: {idioma_txt}")

        if texto_trad and texto_trad.strip() != texto.strip():
            respuesta = (f"🎙️ <b>Transcripción</b> ({esc(idioma_txt)})\n{esc(texto)}\n\n"
                         f"🌐 <b>Traducción al inglés</b>\n{esc(texto_trad)}")
            context.user_data['ultimo_texto_trad'] = texto_trad
            context.user_data['ultimo_texto_trad'] = texto_trad
            plano = f"Transcripción ({idioma_txt})\n{texto}\n\nTraducción al inglés\n{texto_trad}"
        else:
            respuesta = f"🎙️ <b>Transcripción</b> ({esc(idioma_txt)})\n{esc(texto)}"
            plano = texto
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Resumir", callback_data="audio_resumir")]])
        if len(respuesta) > MAX_MSG - 500:
            # Demasiado largo para un mensaje: va en .txt y el aviso queda con el botón de resumir
            await msg.reply_document(document=io.BytesIO(plano.encode('utf-8')), filename="transcripcion.txt")
            await aviso.edit_text(f"🎙️ <b>Transcripción</b> ({esc(idioma_txt)}) — era muy larga, te la mando en el archivo.",
                                  parse_mode='HTML', reply_markup=keyboard)
        else:
            await aviso.edit_text(respuesta, parse_mode='HTML', reply_markup=keyboard)
    except Exception as e:
        logger.error(f"❌ Audio: {e}", exc_info=True)
        await aviso.edit_text(f"❌ Error procesando el audio: {e}")
    finally:
        _borrar(tmp_path)

async def handle_audio_resumir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    texto = context.user_data.get('ultimo_texto')
    if not texto:
        await query.answer("⚠️ No hay texto para resumir.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    try:
        from modules.audio import resumir_texto
        resumen = await asyncio.to_thread(resumir_texto, texto)
        # text_html conserva las negritas del mensaje (con .text se perdían y lo de dentro no iba escapado)
        actual = query.message.text_html or ""
        nuevo = actual + f"\n\n📝 <b>Resumen</b>\n{esc(resumen)}"
        if len(nuevo) > MAX_MSG:
            await query.message.reply_text(f"📝 <b>Resumen</b>\n{esc(resumen)}"[:MAX_MSG], parse_mode='HTML')
        else:
            await query.edit_message_text(nuevo, parse_mode='HTML')
    except Exception as e:
        await query.message.reply_text(f"❌ Error al resumir: {e}")


# --- CHAT WEB BIDIRECCIONAL ---
# Lo ideal es tener los datos en la config («web_db»: {host, database, user, password})
# y borrar de aquí la contraseña. Mientras no esté en la config, se usan estos.
_WEB_DB_POR_DEFECTO = {
    'host': 'mysql-8001.dinaserver.com',
    'database': 'brais_blog',
    'user': 'brais_braisblog',
    'password': 'Br@1sblog!',
}

def get_web_db():
    datos = {**_WEB_DB_POR_DEFECTO, **(user_manager.config.get('web_db') or {})}
    return mysql.connector.connect(**datos, charset='utf8mb4')

def _guardar_respuesta_web(reply_msg_id: int, text: str):
    """Devuelve el session_id si el mensaje respondido era de un chat de la web; None si no."""
    db = get_web_db()
    try:
        cur = db.cursor()
        cur.execute('SELECT session_id FROM chat_sesiones WHERE telegram_msg_id = %s LIMIT 1', (reply_msg_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute('UPDATE chat_sesiones SET brais_reply = %s, brais_typing = 0 WHERE session_id = %s ORDER BY id DESC LIMIT 1',
                    (text, row[0]))
        db.commit()
        return row[0]
    finally:
        db.close()

async def handle_web_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grupo -3 propio. Antes estaba en el 0 delante de wordle: se quedaba con TODAS las
    respuestas en privado (de cualquiera) y wordle no las veía. Ahora solo corta si de
    verdad era una respuesta a un chat de la web."""
    msg = update.message
    if not msg or not msg.reply_to_message: return
    if not user_manager.is_admin(update.effective_user): return
    text = (msg.text or '').strip()
    if not text: return
    reply_msg_id = msg.reply_to_message.message_id
    try:
        session_id = await asyncio.to_thread(_guardar_respuesta_web, reply_msg_id, text)
    except Exception as e:
        logger.error(f"❌ Respuesta web: {e}", exc_info=True)
        await msg.reply_text(f'❌ Error BD: {e}')
        raise ApplicationHandlerStop
    if session_id is None:
        return      # no era un chat de la web: que siga a los demás handlers
    log_in(update, f"Respuesta web → msg_id={reply_msg_id}: {text[:60]}")
    log_out(str(update.effective_user.id), f"Respuesta web enviada a sesión {session_id}")
    await msg.reply_text('✅ Mensaje enviado al usuario en la web.')
    raise ApplicationHandlerStop


# --- ARRANQUE: menú «/» y comprobaciones ---
def _comandos_registrados(app) -> set[str]:
    vistos: set[str] = set()

    def recorrer(h):
        if isinstance(h, CommandHandler):
            vistos.update(h.commands)
        elif isinstance(h, ConversationHandler):
            for x in list(h.entry_points) + list(h.fallbacks):
                recorrer(x)
            for lista in h.states.values():
                for x in lista:
                    recorrer(x)

    for grupo in app.handlers.values():
        for h in grupo:
            recorrer(h)
    return vistos


def _revisar_comandos(app):
    registrados = _comandos_registrados(app)
    catalogo = _todos_los_nombres()
    sin_menu = sorted(registrados - catalogo - COMANDOS_OCULTOS)
    fantasma = sorted(catalogo - registrados)
    if sin_menu:
        logger.info("📋 Comandos que funcionan pero no salen en los menús (añádelos al CATALOGO "
                    "o a COMANDOS_OCULTOS si son privados): " + ", ".join(f"/{c}" for c in sin_menu))
    if fantasma:
        logger.warning("📋 Comandos del menú que NO existen en el bot: " + ", ".join(f"/{c}" for c in fantasma))


# Tipos de mensaje que, si dos handlers de un mismo grupo los esperan, el segundo no se ejecuta nunca.
# (texto que aparece en str(filtro) → nombre para el aviso)
_TIPOS_CHOQUE = {"filters.TEXT": "texto", "filters.PHOTO": "fotos", "application/pdf": "PDF",
                 "image/": "imágenes como archivo", "filters.VOICE": "notas de voz",
                 "filters.AUDIO": "audios", "filters.LOCATION": "ubicaciones"}

def _revisar_grupos(app):
    """Avisa si dos MessageHandler de un mismo grupo esperan el mismo tipo de mensaje
    (lo que rompió el trivial: Papanoelizador y trivial, los dos con texto en -6)."""
    for g, hs in sorted(app.handlers.items()):
        for clave, tipo in _TIPOS_CHOQUE.items():
            quienes = [h for h in hs if isinstance(h, MessageHandler) and clave in str(h.filters)]
            if len(quienes) > 1:
                nombres = ", ".join(f"{h.callback.__module__}.{h.callback.__name__}" for h in quienes)
                logger.warning(f"⚠️ Grupo {g}: varios handlers esperan {tipo} "
                               f"y solo se ejecuta el primero que encaje → {nombres}")


async def post_init(app):
    try:
        cmds = _comandos_menu_slash()
        await app.bot.set_my_commands(cmds)
        logger.info(f"📋 Menú «/» actualizado ({len(cmds)} comandos)")
    except Exception as e:
        logger.warning(f"No pude actualizar el menú «/»: {e}")
    _revisar_comandos(app)
    _revisar_grupos(app)


# --- MAIN ---
# Mapa de grupos (cuanto más negativo, antes se mira). Un grupo por módulo que
# «escucha» texto/fotos/PDF solo cuando espera algo: dentro de un mismo grupo
# solo corre el PRIMER handler que encaja, aunque luego no haga nada.
#   -100 canales · -20 llamadas de voz (bhvoz) · -12 turnos (tur_, /start tur_, comentario/nombre) · -11 botones pql_ · -10 botones img_ · -9 botones arj_/pnl_/triv_ · -8 botones tut_ · -7 trivial
#   -6 papanoel · -5 arrejuntados/miau/login · -3 respuesta chat web · -2 tablón/miau
#   -1 titsa (ForceReply) · 0 resto · 1 catch-all de texto (PDF) · 5 tiempo
#   10-13 ubicaciones · 20 verificador
def main():
    clean_downloads()
    app = (
        Application.builder()
        .token(user_manager.get_token())
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .post_init(post_init)
        .build()
    )

    # ── 0. Inyectar BOT_SECRET en todos los módulos que llaman a la API ────────
    _secret = user_manager.config.get('bot_secret', '') or user_manager.config.get('verificador_secret', '')
    titsa_secret(_secret)
    tranvia_secret(_secret)
    gas_secret(_secret)
    farmacia_secret(_secret)
    camaras_secret(_secret)
    vuelo_secret(_secret)
    crypto_secret(_secret)
    tablon_secret(_secret)

    # Antes que nada: nada de lo que llegue de un canal pasa de aquí
    app.add_handler(TypeHandler(Update, ignorar_canales), group=-100)

    ter_handlers(app)

    # ── 1. Módulos con setup() ────────────────────────────────────────────────
    _arj_secret = user_manager.config.get('arrejuntados_secret', '')
    bingo_setup(app, conn_factory=get_web_db)   # /bingo: balance con la cuenta bhid
    sala_setup(app)
    miau_setup(app, conn_factory=get_web_db)   # MiauCipher: detector de audios + crear/responder
    crypto_setup(app)
    tablon_setup(app)                            # tablón de senderistas: /zonas /publicar /tablon
    enviomagico_setup(app, bot_secret=_secret)   # latido + botón «Cerrar envío» de Envío mágico
    arrejuntados_setup(app, secret=_arj_secret)  # /arrejuntados (secreto propio)
    papanoel_setup(app, secret=_arj_secret)      # /papanoeliza
    bhid_login_setup(app, conn_factory=get_web_db)   # entrar en la app de Belinda con Telegram
    trivial_setup(app, secret=user_manager.config.get('trivial_secret', '') or _arj_secret)   # /trivial (grupo -7)
    tutor_setup(app, secret=user_manager.config.get('tutor_secret', '')
                or user_manager.config.get('trivial_secret', '') or _arj_secret)                # /tutor (botones tut_ en -8)
    amigoinvisible_setup(app, conn_factory=get_web_db)   # /amigoinvisible + /start ai_… (botones aia_/aiq_ en -5)
    pequelab_setup(app)                          # /experimento (PequeLab, solo lectura; botones pql_ en -11)
    turnos_setup(app, secret=user_manager.config.get('turnos_secret', '') or user_manager.config.get('tutor_secret', '')
                 or user_manager.config.get('trivial_secret', '') or _arj_secret)   # /turnos + /start tur_… (botones tur_ y textos en -12)
    bh_voz_setup(app, secret=user_manager.config.get('voz_secret', ''),
                 es_admin=user_manager.is_admin)  # llamadas de voz de la web: respuestas y botones bhvoz: en -20

    # ── 2. ConversationHandlers (ANTES que handlers sueltos) ──────────────────

    # Alertas
    for h in camaras_handlers():    app.add_handler(h)
    for h in despertador_handlers(): app.add_handler(h)
    for h in divisas_handlers():    app.add_handler(h)
    for h in agro_handlers():       app.add_handler(h)

    # Vuelos (ConversationHandler)
    for h in vuelo_handlers():      app.add_handler(h)

    # Tiempo (ConversationHandler, grupo 5 para no bloquear locations de otros)
    for h in tiempo_handlers():     app.add_handler(h, group=5)

    # ERP privados (auth por BD)
    for h in lista_handlers(conn_factory=get_web_db):      app.add_handler(h)
    for h in fichaje_handlers():    app.add_handler(h)

    # ── 3. Comandos simples ───────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler(["comandos", "ayuda", "help"], comandos_command))
    app.add_handler(CommandHandler(["id", "michatid"], id_command))
    app.add_handler(CommandHandler("wordle",    wordle_command))
    app.add_handler(CommandHandler("wranking",  wranking_command))
    app.add_handler(CommandHandler("unir",      unir_command))
    app.add_handler(CommandHandler("listo",     do_merge))
    app.add_handler(CommandHandler("book",      search_books))
    app.add_handler(CommandHandler("leer",      cmd_leer))
    app.add_handler(CommandHandler("stats",     stats))
    app.add_handler(CommandHandler("autorizar", autorizar))
    app.add_handler(CommandHandler("video",     video_command))
    app.add_handler(CommandHandler("music",     music_command))
    app.add_handler(CommandHandler("social",    social_command))

    # Transporte
    for h in titsa_handlers():      app.add_handler(h)
    for h in tranvia_handlers():    app.add_handler(h)
    for h in gas_handlers():        app.add_handler(h)
    for h in farmacia_handlers():   app.add_handler(h)

    # TV
    for h in tv_handlers():         app.add_handler(h)

    # Verificador
    for h in verificador_handlers(config={'bot_secret': _secret}): app.add_handler(h)

    for h in veoveo_handlers(): app.add_handler(h)

    # ── 4. Location handlers (grupos separados para no interferir) ────────────
    app.add_handler(gas_location_handler(),      group=10)
    app.add_handler(titsa_location_handler(),    group=11)
    app.add_handler(farmacia_location_handler(), group=12)
    app.add_handler(tranvia_location_handler(),  group=13)

    # ── 5. Callbacks ─────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(prepare_fill_pdf,     pattern="^option_fill$"))
    app.add_handler(CallbackQueryHandler(convert_pdf_to_word,  pattern="^pdf_to_word$"))
    app.add_handler(CallbackQueryHandler(convert_pdf_to_word,  pattern="^start_conversion$"))
    app.add_handler(CallbackQueryHandler(menu_pdf,             pattern="^menu_pdf$"))
    app.add_handler(CallbackQueryHandler(start_merging,        pattern="^start_merging$"))
    app.add_handler(CallbackQueryHandler(do_merge,             pattern="^do_merge$"))
    app.add_handler(CallbackQueryHandler(handle_audio_resumir, pattern="^audio_resumir$"))
    app.add_handler(CallbackQueryHandler(pdf_callback_handler, pattern=r"^pdf_"))
    app.add_handler(CallbackQueryHandler(image_callback_handler, pattern=r"^img_"), group=-10)
    app.add_handler(CallbackQueryHandler(leer_callback,          pattern=r"^leer_voice_|^leer_cancel$"))
    app.add_handler(CallbackQueryHandler(leer_trigger_callback,  pattern=r"^leer_trigger$"))
    app.add_handler(CallbackQueryHandler(book_callback_handler,  pattern=r"^bk_"))
    app.add_handler(CallbackQueryHandler(media_callback_handler,       pattern=r"^(yt_|music_)"))
    app.add_handler(CallbackQueryHandler(media_offer_callback_handler, pattern=r"^media_offer_"))
    app.add_handler(CallbackQueryHandler(menu_handler,                 pattern=r"^menu_"))

    # ── 6. Message handlers (orden crítico) ──────────────────────────────────
    app.add_handler(MessageHandler(filters.VOICE,                        handle_audio))
    app.add_handler(MessageHandler(filters.AUDIO,                        handle_audio))
    # Respuestas de Brais a los chats de la web: grupo propio, solo corta si era de la web
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.REPLY & filters.ChatType.PRIVATE,
        handle_web_reply
    ), group=-3)
    app.add_handler(MessageHandler(filters.Document.PDF,                 handle_pdf_or_leer))
    app.add_handler(MessageHandler(filters.Document.MimeType("application/epub+zip") |
                                   filters.Document.MimeType("application/vnd.openxmlformats-officedocument.wordprocessingml.document") |
                                   filters.Document.MimeType("text/plain"),
                                   leer_document_handler))
    app.add_handler(MessageHandler(filters.PHOTO,                        handle_photo))

    # Verificador: detección automática en grupo alto (no intercepta audio/voz)
    for h in verificador_offer_handlers(): app.add_handler(h, group=20)

    # titsa text handler en grupo -1 (respuestas ForceReply)
    app.add_handler(titsa_text_handler(), group=-1)

    # wordle en el grupo 0
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wordle_texto))
    # catch-all de texto (relleno de PDF) — grupo 1 PROPIO; en el 0 no llegaba a ejecutarse
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_handler), group=1)

    app.add_error_handler(error_handler)

    logger.info("=" * 50)
    logger.info("🚀 Bot arrancado — esperando mensajes")
    logger.info("=" * 50)
    # ALL_TYPES: el trivial necesita las respuestas a las encuestas (poll_answer)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
