import os
import json
import asyncio
from pathlib import Path
from telegram import Bot
from user_manager import user_manager

# Configuración
IMPORT_DIR = Path("libros_locales")
CACHE_FILE = Path("cache_libros.json")

async def importar_libros():
    token = user_manager.get_token()
    if not token or "TOKEN" in token:
        print("❌ Error: Configura el token en config.json primero.")
        return

    bot = Bot(token)
    
    # Cargar caché existente
    cache = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    # Obtener tu ID de la whitelist para saber a quién enviar los archivos
    # Usaremos el primer admin de la lista para el envío
    admin_username = user_manager.config.get("admins", [None])[0]
    if not admin_username:
        print("❌ Error: No hay admins configurados en config.json")
        return

    # IMPORTANTE: Necesitamos tu ID numérico, no el @username. 
    # El script te lo pedirá la primera vez.
    print("--- IMPORTADOR MASIVO DE LIBROS ---")
    chat_id = input("Introduce tu ID numérico de Telegram (puedes obtenerlo en @userinfobot): ")

    files = list(IMPORT_DIR.glob('*.*'))
    if not files:
        print(f"⚠️ No hay archivos en {IMPORT_DIR}")
        return

    print(f"🚀 Iniciando subida de {len(files)} libros...")

    for file_path in files:
        # Usamos el nombre del archivo (sin extensión) como clave de búsqueda
        # Limpiamos puntos y guiones para que coincida mejor
        book_key = file_path.stem.replace("_", " ").replace(".", " ").lower()
        
        if book_key in cache:
            print(f"⏩ Saltando (ya en caché): {file_path.name}")
            continue

        try:
            print(f"📤 Subiendo: {file_path.name}...")
            with open(file_path, 'rb') as f:
                # Enviamos el documento a tu chat
                msg = await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    caption=f"📦 Libro indexado: {file_path.name}"
                )
                
                # Guardamos el file_id en el caché
                cache[book_key] = msg.document.file_id
                
            # Guardar progreso en cada paso por si falla
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=4)
                
            await asyncio.sleep(2) # Evitar ban de Telegram por flood
        except Exception as e:
            print(f"❌ Error subiendo {file_path.name}: {e}")

    print("\n✅ Proceso finalizado. El caché ha sido actualizado.")

if __name__ == "__main__":
    asyncio.run(importar_libros())