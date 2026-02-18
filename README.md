# 🤖 Multi-Tool Media & Library Bot

Un bot de Telegram avanzado y versátil diseñado como una navaja suiza de utilidades. Permite desde descargar contenido de casi cualquier red social hasta editar PDFs, procesar imágenes con IA y gestionar una biblioteca masiva de libros.

## ✨ Características Principales

### 📹 Media & Redes Sociales
- **YouTube Pro:** Búsqueda integrada y descarga en MP3/MP4. Incluye bypass de firmas (`n-challenge`) mediante Node.js y compresión inteligente con FFmpeg para archivos >50MB.
- **Social Downloader:** Descarga directa de vídeos de **TikTok, Instagram, Twitter/X** con solo enviar el enlace.

### 📚 Gestión de Libros (E-books)
- **Búsqueda en LibGen:** Encuentra libros directamente en múltiples mirrors de Library Genesis.
- **Biblioteca Local:** Sistema de caché para entrega inmediata de libros almacenados localmente.
- **Importador Masivo:** Script dedicado (`importador.py`) para indexar automáticamente cientos de libros locales en la nube de Telegram.
- **Buscador Inteligente:** Si no hay resultados directos, ofrece enlaces profundos a Z-Library y Biblioteca Secreta.
- **Auto-Updater:** Rastreador automático para localizar el username más reciente del bot de Biblioteca Secreta.

### 🖼️ Procesamiento de Imágenes
- **Rembg Integration:** Elimina el fondo de cualquier imagen automáticamente.
- **Sticker Ready:** Ajusta y redimensiona imágenes automáticamente al formato requerido por Telegram (512px) para stickers.

### 📄 Utilidades PDF
- **Rellenado Inteligente:** Escaneo de campos rellenables en archivos PDF mediante detección de patrones (puntos/guiones).
- **Inyección de Texto:** Superposición de respuestas sobre el PDF original manteniendo el formato.

## 📂 Estructura del Proyecto

```text
.
├── bot_main.py           # Núcleo del bot y registro de comandos
├── user_manager.py       # Gestión de usuarios, logs y permisos
├── importador.py         # Script para subir e indexar libros locales
├── config.json           # Configuración (Token, IDs) [Ignorado en Git]
├── cache_libros.json     # Índice de file_ids de libros [Ignorado en Git]
├── modules/
│   ├── media.py          # YouTube, descarga CLI y compresión FFmpeg
│   ├── libros.py         # Búsqueda en LibGen y gestión de caché
│   ├── social.py         # Descarga de TikTok, Instagram, X/Twitter
│   ├── images.py         # Eliminación de fondos y redimensión de stickers
│   ├── pdf_parser.py     # Detección de campos en documentos PDF
│   ├── pdf_editor.py     # Generación y mezcla de capas sobre PDF
│   └── updater.py        # Crawler para Biblioteca Secreta
└── downloads/            # Almacenamiento temporal [Ignorado en Git]
```
🛠️ Requisitos del Sistema
Python 3.10+

Node.js (Indispensable para descargar de YouTube).

FFmpeg (Para la compresión de vídeo).

Dependencias:

pip install python-telegram-bot yt-dlp requests beautifulsoup4 rembg Pillow pypdf reportlab pdfminer.six

🚀 Uso del Importador de Libros
Si tienes una colección de libros en la carpeta libros_locales y quieres que el bot los encuentre al instante:

Coloca tus archivos en libros_locales/.

Ejecuta: python importador.py.

Introduce tu ID numérico de Telegram cuando se te solicite.

El script subirá los libros a tu chat y guardará los file_id en cache_libros.json para que el bot pueda reenviarlos instantáneamente sin volver a subirlos.

📜 Licencia
Este proyecto es de código abierto bajo la licencia MIT.

## 🚀 Instalación y Configuración

1. **Clonar el repositorio:**
  
   git clone https://github.com/braishernandez/BB-BraisBot.git
   cd BB-BraisBot
   
2 Instalar dependencias de Python:
  pip install -r requirements.txt

3 Configurar las credenciales:

  Renombra config.json.example a config.json.

  Edita config.json con tu Token de BotFather y tu ID de Telegram.

4 Cookies de YouTube:

Para evitar bloqueos, exporta tus cookies de YouTube en formato Netscape y guárdalas como www.youtube.com_cookies.txt en la raíz del proyecto.


Solución de Problemas Comunes
Error: "Request Entity Too Large": Telegram limita los bots a 50MB. El bot intentará comprimir el vídeo, pero si tras la compresión sigue superando el límite, no podrá enviarse.

Error de Signaturas (n-challenge): Asegúrate de que node -v funciona en tu terminal. El bot utiliza Node.js para descifrar los algoritmos de YouTube.

Caché corrupta: El bot limpia automáticamente la caché de yt-dlp en cada descarga para evitar errores de sesiones antiguas.


---
