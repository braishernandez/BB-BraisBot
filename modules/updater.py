import requests
from bs4 import BeautifulSoup
import re
from user_manager import user_manager

def get_latest_biblioteca_bot():
    url = "http://bibliotecasecreta.nl/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Buscamos enlaces que contengan t.me
        links = soup.find_all('a', href=re.compile(r't.me/'))
        
        for link in links:
            href = link.get('href')
            # Filtramos para encontrar el que parece el bot de descarga
            if "Bot" in href or "biblioteca" in href.lower():
                bot_username = href.split('/')[-1]
                return bot_username
                
        return "BibliotecaSecreta9889Bot" # Fallback si no encuentra nada
    except Exception as e:
        print(f"Error rastreando bibliotecasecreta.nl: {e}")
        return "BibliotecaSecreta9889Bot"