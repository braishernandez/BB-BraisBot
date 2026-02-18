import yt_dlp
import os
from pathlib import Path
from user_manager import user_manager

DOWNLOAD_DIR = Path("downloads")

async def handle_social_link(update, context):
    url = update.message.text
    user = update.effective_user.username
    
    # Filtro básico para ver si es un link de redes
    if not any(x in url for x in ['tiktok.com', 'instagram.com', 'twitter.com', 'x.com']):
        return 

    user_manager.log(user, "Enlace social detectado", url)
    status_msg = await update.message.reply_text("📱 Procesando video de red social...")
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(DOWNLOAD_DIR / '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
        size = os.path.getsize(filename) // (1024 * 1024)
        await update.message.reply_video(
            video=open(filename, 'rb'),
            caption=f"✅ Video descargado de {info.get('extractor_key', 'Red Social')}"
        )
        
        user_manager.log(user, "Video social enviado", f"{size}MB")
        
        if os.path.exists(filename):
            os.remove(filename)
        await status_msg.delete()
        
    except Exception as e:
        user_manager.log(user, "Error en social", str(e))
        await status_msg.edit_text(f"❌ No se pudo descargar el video. Puede que sea privado o el link haya expirado.")