"""
Módulo de transcripción de audios con Whisper (Windows + CUDA)
"""
import os
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

def transcribir(audio_path, modelo='small'):
    """Transcribe el audio y devuelve texto + idioma."""
    tmp_wav = tempfile.mktemp(suffix='.wav')
    try:
        audio_a_wav(audio_path, tmp_wav)
        model = get_model(modelo)
        result = model.transcribe(tmp_wav, task='transcribe')
        idioma = result.get('language', '?')
        return {
            'texto': result['text'].strip(),
            'idioma': idioma,
            'idioma_nombre': IDIOMAS.get(idioma, idioma),
            'segmentos': result.get('segments', []),
        }
    finally:
        if os.path.exists(tmp_wav):
            try: os.unlink(tmp_wav)
            except: pass

def traducir(audio_path, modelo='small'):
    """Traduce el audio al inglés con Whisper."""
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
    """
    Genera un resumen extractivo simple del texto.
    Sin LLM externo — selecciona las frases más representativas.
    """
    import re
    frases = re.split(r'(?<=[.!?])\s+', texto.strip())
    frases = [f.strip() for f in frases if len(f.strip()) > 20]
    if not frases:
        return texto

    # Si es corto, devolver tal cual
    if len(frases) <= 3:
        return texto

    # Tomar primera, última y las más largas del medio como resumen
    n = max(2, len(frases) // 3)
    medio = sorted(frases[1:-1], key=len, reverse=True)[:n]
    # Reordenar por posición original
    orden = {f: i for i, f in enumerate(frases)}
    seleccion = sorted([frases[0]] + medio + [frases[-1]], key=lambda f: orden.get(f, 0))
    return ' '.join(seleccion)
