"""
Módulo de transcripción de audios con Whisper (Windows + CUDA)
"""
import os
import time
import tempfile
import subprocess

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

# Modelo global cargado una sola vez
_model = None

def get_model(modelo='small'):
    global _model
    if _model is None:
        import whisper
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"[audio] Cargando modelo {modelo} en {device}...")
        _model = whisper.load_model(modelo, device=device)
        print(f"[audio] Modelo cargado.")
    return _model

def audio_a_wav(entrada, salida_wav):
    cmd = ['ffmpeg', '-y', '-i', entrada, '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', salida_wav]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"Error convirtiendo audio: {r.stderr.decode()[-200:]}")

def duracion_audio(audio_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
           '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return float(r.stdout.strip())
    except:
        return 0.0

def transcribir(audio_path, modelo='small'):
    tmp_wav = tempfile.mktemp(suffix='.wav')
    try:
        duracion = duracion_audio(audio_path)
        audio_a_wav(audio_path, tmp_wav)
        model = get_model(modelo)
        t_inicio = time.time()
        result = model.transcribe(tmp_wav, task='transcribe')
        t_total = time.time() - t_inicio
        idioma = result.get('language', '?')
        return {
            'texto': result['text'].strip(),
            'idioma': idioma,
            'idioma_nombre': IDIOMAS.get(idioma, idioma),
            'segmentos': result.get('segments', []),
            'duracion_seg': duracion,
            'tiempo_proceso': t_total,
        }
    finally:
        if os.path.exists(tmp_wav):
            try: os.unlink(tmp_wav)
            except: pass

def traducir(audio_path, modelo='small'):
    tmp_wav = tempfile.mktemp(suffix='.wav')
    try:
        audio_a_wav(audio_path, tmp_wav)
        model = get_model(modelo)
        result = model.transcribe(tmp_wav, task='translate')
        return result['text'].strip()
    finally:
        if os.path.exists(tmp_wav):
            try: os.unlink(tmp_wav)
            except: pass

def resumir_texto(texto):
    import re
    frases = re.split(r'(?<=[.!?])\s+', texto.strip())
    frases = [f.strip() for f in frases if len(f.strip()) > 20]
    if not frases:
        return texto
    if len(frases) <= 3:
        return texto
    n = max(2, len(frases) // 3)
    medio = sorted(frases[1:-1], key=len, reverse=True)[:n]
    orden = {f: i for i, f in enumerate(frases)}
    seleccion = sorted([frases[0]] + medio + [frases[-1]], key=lambda f: orden.get(f, 0))
    return ' '.join(seleccion)
