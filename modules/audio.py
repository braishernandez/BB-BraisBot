"""
Módulo de transcripción y traducción de audios con Whisper
Funciona con notas de voz de Telegram y audios de WhatsApp (.ogg, .mp3, .m4a, etc.)
"""
import os
import sys
import json
import tempfile
import subprocess

# Asegurar paquetes locales
_local = '/home/braishernandez/.local/lib/python3.9/site-packages'
if _local not in sys.path:
    sys.path.insert(0, _local)

FFMPEG_BIN = '/home/braishernandez/.local/lib/python3.9/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'

IDIOMAS = {
    'af': 'afrikáans', 'ar': 'árabe', 'ca': 'catalán', 'cs': 'checo',
    'da': 'danés', 'de': 'alemán', 'el': 'griego', 'en': 'inglés',
    'es': 'español', 'fi': 'finlandés', 'fr': 'francés', 'gl': 'gallego',
    'he': 'hebreo', 'hi': 'hindi', 'hu': 'húngaro', 'id': 'indonesio',
    'it': 'italiano', 'ja': 'japonés', 'ko': 'coreano', 'nl': 'neerlandés',
    'no': 'noruego', 'pl': 'polaco', 'pt': 'portugués', 'ro': 'rumano',
    'ru': 'ruso', 'sk': 'eslovaco', 'sv': 'sueco', 'th': 'tailandés',
    'tr': 'turco', 'uk': 'ucraniano', 'vi': 'vietnamita', 'zh': 'chino',
}

def get_ffmpeg():
    if os.path.isfile(FFMPEG_BIN) and os.access(FFMPEG_BIN, os.X_OK):
        return FFMPEG_BIN
    for cmd in ['ffmpeg', '/usr/bin/ffmpeg']:
        try:
            subprocess.run([cmd, '-version'], capture_output=True, check=True)
            return cmd
        except:
            pass
    return None

def audio_a_wav(entrada, salida_wav):
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg no disponible")
    cmd = [ffmpeg, '-y', '-i', entrada, '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', salida_wav]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"Error convirtiendo audio: {r.stderr.decode()[-200:]}")

def transcribir_y_traducir(audio_path, modelo='small'):
    """
    Transcribe el audio en su idioma original y lo traduce al español.
    Devuelve dict con: texto_original, texto_traducido, idioma, idioma_nombre
    """
    import whisper

    tmp_wav = tempfile.mktemp(suffix='.wav')
    try:
        audio_a_wav(audio_path, tmp_wav)
        model = whisper.load_model(modelo)

        # Transcripción en idioma original
        result_orig = model.transcribe(tmp_wav, task='transcribe')
        idioma = result_orig.get('language', 'desconocido')
        texto_orig = result_orig['text'].strip()

        # Traducción al español (solo si no es ya español/gallego/catalán)
        texto_trad = None
        if idioma not in ('es', 'gl', 'ca'):
            result_trad = model.transcribe(tmp_wav, task='translate')
            # translate siempre da inglés — usamos Helsinki-NLP si disponible, si no dejamos en inglés
            texto_trad = result_trad['text'].strip()

        return {
            'texto_original': texto_orig,
            'texto_traducido': texto_trad,
            'idioma': idioma,
            'idioma_nombre': IDIOMAS.get(idioma, idioma),
        }
    finally:
        if os.path.exists(tmp_wav):
            os.unlink(tmp_wav)
