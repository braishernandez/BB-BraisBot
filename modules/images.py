import io
from rembg import remove
from PIL import Image

def remove_background(image_bytes):
    try:
        # Forzamos que la entrada sean bytes y la salida también
        input_data = bytes(image_bytes)
        result = remove(input_data)
        return result
    except Exception as e:
        print(f"Error en rembg: {e}")
        return image_bytes

def prepare_sticker(image_bytes):
    """Ajusta la imagen para cumplir con los requisitos de Telegram (512px)"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    
    ww, hh = img.size
    if ww > hh:
        new_w = 512
        new_h = int(hh * (512 / ww))
    else:
        new_h = 512
        new_w = int(ww * (512 / hh))
        
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio