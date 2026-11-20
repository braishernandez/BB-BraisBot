import json
import os
import logging
from datetime import datetime
from pathlib import Path

class UserManager:
    def __init__(self):
        self.file = 'config.json'
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        if not os.path.exists(self.file):
            self.create_default_config()
            
        self.config = self.load_config()
        self.setup_logging()

    def create_default_config(self):
        default_data = {
            # El token NUNCA va en el código (el repositorio es público): ponlo en config.json
            "bot_token": "",
            "whitelist": ["braish"],
            "admins": ["braish"],
            "zlib_url": "https://z-lib.id",
            "biblioteca_bot": "BibliotecaSecreta9889Bot"
        }
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)

    def load_config(self):
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def setup_logging(self):
        date_str = datetime.now().strftime("%Y%m%d")
        fmt = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.logger = logging.getLogger('bot_logger')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        
        ch = logging.StreamHandler()
        fh = logging.FileHandler(self.log_dir / f'actividad_{date_str}.log', encoding='utf-8')
        
        ch.setFormatter(fmt)
        fh.setFormatter(fmt)
        self.logger.addHandler(ch)
        self.logger.addHandler(fh)

    def log(self, user, accion, detalles="", origen="PRIVADO"):
        """Registra la actividad con origen (Privado o Grupo)"""
        msg = f"[{origen}] 👤 @{user if user else 'Anon'} - {accion}"
        if detalles: 
            msg += f" - {detalles}"
        
        # El logger ya se encarga de imprimir en consola y guardar en archivo
        self.logger.info(msg)

    def get_token(self): return self.config.get('bot_token')

    @staticmethod
    def _claves(user):
        """Identificadores de un usuario para comparar con las listas: el @usuario en
        minúsculas (Telegram no distingue mayúsculas) y su ID numérico. Acepta un
        telegram.User o un texto (usuario o ID)."""
        if user is None:
            return set()
        if isinstance(user, (str, int)):
            return {str(user).lstrip('@').lower()}
        claves = set()
        if getattr(user, 'username', None):
            claves.add(user.username.lower())
        if getattr(user, 'id', None):
            claves.add(str(user.id))
        return claves

    def _en_lista(self, user, lista):
        permitidos = {str(x).lstrip('@').lower() for x in self.config.get(lista, [])}
        return bool(self._claves(user) & permitidos)

    def is_authorized(self, user): return self._en_lista(user, 'whitelist') or self.is_admin(user)
    def is_admin(self, user): return self._en_lista(user, 'admins')

    def autorizar(self, quien):
        """Añade un @usuario o un ID a la lista blanca (sin duplicados). Devuelve el texto guardado."""
        quien = str(quien).strip().lstrip('@')
        lista = self.config.setdefault('whitelist', [])
        if quien.lower() not in {str(x).lower() for x in lista}:
            lista.append(quien)
            self._save()
        return quien
    def get_zlib_url(self): return self.config.get('zlib_url', 'https://z-lib.id')
    
    def set_zlib_url(self, url):
        self.config['zlib_url'] = url
        self._save()

    def get_biblioteca_bot(self):
        return self.config.get('biblioteca_bot', 'BibliotecaSecreta9889Bot')

    def set_biblioteca_bot(self, bot_username):
        self.config['biblioteca_bot'] = bot_username
        self._save()

    def _save(self):
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)

# Instanciamos el manager para que pueda ser importado por bot_main.py
user_manager = UserManager()