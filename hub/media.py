"""Shared remote controls for the Windows tablet and the Android app."""
import html
import json
import queue
import re
import threading
import time
import unicodedata
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

APPS = {
    'youtube': ('YouTube', 'https://www.youtube.com/'),
    'music': ('YouTube Music', 'https://music.youtube.com/'),
    'spotify': ('Spotify', 'https://open.spotify.com/'),
    'instagram': ('Instagram', 'https://www.instagram.com/'),
}
CONTROLS = {'trip', 'apps', 'expand', 'playpause', 'next', 'previous', 'mute', 'volumeup', 'volumedown'}
ORDINALS = {'primeiro': 1, 'primeira': 1, 'segundo': 2, 'segunda': 2, 'terceiro': 3, 'terceira': 3,
            'quarto': 4, 'quarta': 4, 'quinto': 5, 'quinta': 5}


def parse_command(phrase):
    original = phrase.strip()
    folded = ''.join(ch for ch in unicodedata.normalize('NFD', original.casefold())
                     if unicodedata.category(ch) != 'Mn')
    order = re.fullmatch(r'(?:ok max[ ,]+)?(?:(?:coloca|coloque|toque|toca|abre|abra|escolha)\s+)?(?:[oa]\s+)?(primeir[oa]|segund[oa]|terceir[oa]|quart[oa]|quint[oa])(?:\s+(?:video|resultado))?[.!]?', folded)
    if order:
        return {'action': 'result', 'index': ORDINALS[order[1]]}
    if re.search(r'\b(expanda|expandir|maximizar|maximize)\b', folded):
        return {'action': 'expand'}
    for pattern, action in ((r'paus[ae]|play|retom[ae]', 'playpause'),
                            (r'proxim[ao]|avanc[ae]', 'next'), (r'anterior|volt[ae]', 'previous')):
        if re.fullmatch(rf'(?:ok max[ ,]+)?(?:{pattern})(?:\b.*)?', folded):
            return {'action': action}
    if re.search(r'\b(?:viagem|painel)\b', folded):
        return {'action': 'trip'}
    if 'spotify' in folded:
        return {'action': 'open', 'app': 'spotify'}
    if 'instagram' in folded:
        return {'action': 'open', 'app': 'instagram'}
    if 'youtube music' in folded:
        return {'action': 'open', 'app': 'music'}
    parts = re.split(r'\b(?:coloca|coloque|p[oõ]e|tocar|toca|toque|buscar|busca|busque|procure|pesquise)\s+', original,
                     maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2 and parts[1].strip():
        query = re.sub(r'\s+(?:no\s+)?youtube\s*$', '', parts[1], flags=re.IGNORECASE)
        return {'action': 'search', 'query': query.strip(' ,.')}
    if 'youtube' in folded:
        return {'action': 'open', 'app': 'youtube'}
    return None


def youtube_results(query, key):
    params = urlencode({'part': 'snippet', 'type': 'video', 'maxResults': 5,
                        'regionCode': 'BR', 'relevanceLanguage': 'pt', 'q': query, 'key': key})
    with urlopen('https://www.googleapis.com/youtube/v3/search?' + params, timeout=5) as response:
        data = json.loads(response.read(256_000))
    videos = []
    for item in data.get('items', []):
        identifier = item.get('id', {}).get('videoId', '')
        snippet = item.get('snippet', {})
        if re.fullmatch(r'[\w-]{11}', identifier, re.ASCII):
            videos.append({'id': identifier, 'title': html.unescape(snippet.get('title', 'Vídeo'))[:180],
                           'channel': html.unescape(snippet.get('channelTitle', ''))[:100]})
    return videos


class Media:
    def __init__(self, key=''):
        self.key = key
        self.lock = threading.Lock()
        self.actions = queue.Queue(maxsize=12)
        self.results = []
        self.query = ''
        self.notice = 'Abra o tablet no PC ou use os controles abaixo.'
        self.tab = 'trip'
        self.expanded = False
        self.search_started = float('-inf')

    def snapshot(self):
        with self.lock:
            return {'results': self.results.copy(), 'query': self.query, 'notice': self.notice,
                    'tab': self.tab, 'expanded': self.expanded, 'numbered': bool(self.key)}

    def update_layout(self, tab, expanded):
        with self.lock:
            self.tab, self.expanded = tab, expanded

    def _send(self, action, url=None):
        try:
            self.actions.put_nowait((action, url))
            return True, 'Comando enviado ao PC.'
        except queue.Full:
            return False, 'O tablet está ocupado. Tente de novo.'

    def perform(self, data):
        if not isinstance(data, dict):
            return False, 'Comando inválido.'
        action = data.get('action')
        if not isinstance(action, str):
            return False, 'Comando inválido.'
        if action == 'voice':
            phrase = data.get('phrase')
            command = parse_command(phrase) if isinstance(phrase, str) and 0 < len(phrase) <= 180 else None
            if command is None:
                return False, 'Tente “Ok Max, procure um artista” ou “coloque o primeiro”.'
            return self.perform(command)
        if action in CONTROLS:
            return self._send(action)
        if action == 'open':
            app = data.get('app')
            if isinstance(app, str) and app in APPS:
                return self._send('open', APPS[app][1])
        if action == 'result':
            index = data.get('index')
            with self.lock:
                if data.get('query', self.query) == self.query and type(index) is int and 1 <= index <= len(self.results):
                    video = self.results[index-1]['id']
                    return self._send('open', 'https://www.youtube.com/watch?v=' + video)
            return False, 'Faça uma busca que mostre resultados numerados primeiro.'
        if action == 'search':
            query = data.get('query')
            if isinstance(query, str) and 0 < len(query.strip()) <= 100:
                return self.search(query.strip())
        return False, 'Comando inválido.'

    def search(self, query):
        with self.lock:
            now = time.monotonic()
            if now - self.search_started < 3:
                return False, 'Aguarde alguns segundos antes de buscar novamente.'
            self.search_started = now
            self.query = query
            self.results = []
            key = self.key
        if not key:
            sent, notice = self._send('open', APPS['youtube'][1] + 'results?' + urlencode({'search_query': query}))
            if sent:
                notice = 'Busca aberta no YouTube no PC. Para numerar resultados, configure a API no Hub.'
        else:
            try:
                videos = youtube_results(query, key)
            except (LookupError, TypeError, ValueError, OSError, URLError):
                videos = []
                notice = 'A busca falhou. Confira a configuração da API do YouTube no PC.'
            else:
                notice = f'{len(videos)} resultado(s). Diga ou toque no número do vídeo.' if videos else 'Nenhum vídeo encontrado.'
            with self.lock:
                if self.search_started == now:
                    self.results = videos
            if videos:
                self._send('apps')
        with self.lock:
            if self.search_started == now:
                self.notice = notice
        return True, notice
