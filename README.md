# 🤖 BB-BraisBot — Multi-Tool Telegram Bot

Un bot de Telegram avanzado y versátil diseñado como una navaja suiza de utilidades. Desde descargar contenido de redes sociales hasta transcribir audios con IA, editar PDFs y gestionar una biblioteca masiva de libros.

---

## ✨ Características Principales

### 🎙️ Transcripción y Traducción de Audio *(NEW)*
- **Whisper AI:** Transcripción de notas de voz y audios con el modelo `small` de OpenAI Whisper.
- **GPU Accelerated:** Usa CUDA automáticamente si hay GPU Nvidia disponible (recomendado GTX 1050 Ti o superior).
- **Multiidioma:** Detecta el idioma automáticamente. Si no es español/gallego/catalán, traduce al inglés.
- **Resumen con un clic:** Botón inline 📝 Resumir tras cada transcripción — resumen extractivo en local, sin APIs externas.
- **Formatos soportados:** OGG (notas de voz WhatsApp/Telegram), MP3, M4A, WAV y más.
- **Sin autenticación requerida:** Cualquier usuario puede usar esta función, sin necesidad de estar en la whitelist.

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
- **Rellenado Inteligente:** Escaneo de campos rellenables en archivos PDF mediante detección de patrones.
- **Inyección de Texto:** Superposición de respuestas sobre el PDF original manteniendo el formato.
- **Merge tool:** Une múltiples documentos PDF en uno solo.
- **Convertidor:** Transforma PDF a Word (.docx) manteniendo la estructura.

---

## 📂 Estructura del Proyecto

```text
.
├── bot_main.py           # Núcleo del bot y registro de comandos
├── user_manager.py       # Gestión de usuarios, logs y permisos
├── importador.py         # Script para subir e indexar libros locales
├── config.json           # Configuración (Token, IDs) [Ignorado en Git]
├── cache_libros.json     # Índice de file_ids de libros [Ignorado en Git]
├── modules/
│   ├── audio.py          # Transcripción Whisper, traducción y resumen
│   ├── media.py          # YouTube, descarga CLI y compresión FFmpeg
│   ├── libros.py         # Búsqueda en LibGen y gestión de caché
│   ├── social.py         # Descarga de TikTok, Instagram, X/Twitter
│   ├── images.py         # Eliminación de fondos y redimensión de stickers
│   ├── pdf_parser.py     # Detección de campos en documentos PDF
│   ├── pdf_editor.py     # Generación y mezcla de capas sobre PDF
│   └── updater.py        # Crawler para Biblioteca Secreta
└── downloads/            # Almacenamiento temporal [Ignorado en Git]
```

---

## 🛠️ Requisitos del Sistema

- **Python 3.10+**
- **Node.js** — Indispensable para descargar de YouTube.
- **FFmpeg** — Para conversión y compresión de audio/vídeo.
- **GPU Nvidia** *(opcional pero recomendado)* — Acelera la transcripción con CUDA.

---

## 🚀 Instalación y Configuración

### 1. Clonar el repositorio

```bash
git clone https://github.com/braishernandez/BB-BraisBot.git
cd BB-BraisBot
```

### 2. Instalar dependencias de Python

```bash
pip install -r requirements.txt
```

### 3. Instalar PyTorch con soporte CUDA *(GPU Nvidia)*

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

> Si no tienes GPU Nvidia, omite este paso. El bot usará CPU automáticamente (más lento para transcripción).

### 4. Configurar las credenciales

Renombra `config.json.example` a `config.json` y edítalo:

```json
{
    "bot_token": "TU_TOKEN_DE_BOTFATHER",
    "whitelist": ["tu_username"],
    "admins": ["tu_username"]
}
```

### 5. Cookies de YouTube *(opcional)*

Para evitar bloqueos, exporta tus cookies de YouTube en formato Netscape y guárdalas como `www.youtube.com_cookies.txt` en la raíz del proyecto.

### 6. Iniciar el bot

```bash
python bot_main.py
```

---

## 🎙️ Uso de Transcripción de Audio

1. Envía una nota de voz o archivo de audio al bot.
2. El bot transcribirá el audio automáticamente.
3. Si el audio no está en español, se añadirá también la traducción al inglés.
4. Pulsa el botón **📝 Resumir** para obtener un resumen del contenido.

> La primera ejecución descargará el modelo Whisper `small` (~244MB). Las siguientes serán instantáneas.

---

## 📚 Uso del Importador de Libros

1. Coloca tus archivos en `libros_locales/`.
2. Ejecuta: `python importador.py`
3. Introduce tu ID numérico de Telegram cuando se te solicite.

El script subirá los libros a tu chat y guardará los `file_id` en `cache_libros.json` para reenvíos instantáneos.

---

## 🐛 Solución de Problemas

| Error | Solución |
|---|---|
| `Request Entity Too Large` | Telegram limita a 50MB. El bot intenta comprimir el vídeo automáticamente. |
| Error de firmas YouTube (`n-challenge`) | Asegúrate de que `node -v` funciona en tu terminal. |
| Caché corrupta | El bot limpia automáticamente la caché de yt-dlp en cada descarga. |
| Transcripción lenta | Instala PyTorch con CUDA para usar la GPU. |
| `ffmpeg not found` | Asegúrate de que ffmpeg está instalado y en el PATH del sistema. |

---

## 📜 Licencia

Este proyecto es de código abierto bajo la licencia MIT.
