"""Max GPS LAN API and read-only receiver for the SCS plugin."""
import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import math
import os
import queue
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from hub.media import Media
from hub.road_alerts import RoadAlerts, import_points
from hub.pairing import LocalPairing

ASSETS = Path(__file__).resolve().parent / 'web'
REQUIRED = ('speed', 'distance', 'seconds', 'limit', 'x', 'z', 'heading')
NUMERIC = ('fuel', 'fuelCapacity', 'rpm', 'cruise', 'odometer', 'wear', 'gear', 'income')
LABELS = ('truckName', 'cargo', 'origin', 'delivery')
MAX_MAP_BYTES = 32 * 1024 * 1024


def number(value):
    return type(value) in (int, float) and abs(value) <= 1e18 and math.isfinite(value)


def decode(payload):
    try:
        data = json.loads(payload.decode('utf-8', errors='replace'))
        if not isinstance(data, dict) or not all(number(data.get(key)) for key in REQUIRED):
            return None
        result = {key: data[key] for key in REQUIRED}
        result.update({key: data[key] for key in NUMERIC if number(data.get(key))})
        result.update({key: data[key][:160] for key in LABELS if isinstance(data.get(key), str)})
        if type(data.get('paused')) is bool:
            result['paused'] = data['paused']
        return result
    except (ValueError, TypeError, RecursionError):
        return None


def read_map(path):
    if path.stat().st_size > MAX_MAP_BYTES:
        raise ValueError('Mapa maior que 32 MB.')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict) and 'version' not in data and isinstance(data.get('edges'), list):
        # Import a locally exported Truck Dash graph. Bit 1 marks ferries;
        # bit 2 marks roads that only permit travel from a to b.
        roads = []
        for edge in data['edges']:
            if not isinstance(edge, list) or len(edge) < 4 or type(edge[3]) is not int:
                raise ValueError('Trecho inválido no grafo exportado.')
            if not edge[3] & 1:
                roads.append([edge[0], edge[1], int(bool(edge[3] & 2))])
        data = {'version': 1, 'name': path.stem, 'nodes': data.get('nodes'), 'roads': roads}
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Formato de mapa Max GPS v1 inválido.')
    name, nodes, roads = data.get('name'), data.get('nodes'), data.get('roads')
    if not isinstance(name, str) or not name.strip() or not isinstance(nodes, list) or not isinstance(roads, list):
        raise ValueError('O mapa precisa de nome, pontos e estradas.')
    if not 2 <= len(nodes) <= 200_000 or not 1 <= len(roads) <= 400_000:
        raise ValueError('Quantidade de pontos ou estradas fora do limite.')
    for node in nodes:
        if (not isinstance(node, list) or len(node) not in (2, 3) or
                not all(number(value) and abs(value) < 10_000_000 for value in node[:2]) or
                (len(node) == 3 and not isinstance(node[2], str))):
            raise ValueError('Cada ponto deve conter X, Z e um nome opcional.')
    for road in roads:
        if (not isinstance(road, list) or len(road) != 3 or
                not all(type(value) is int for value in road) or
                not all(0 <= index < len(nodes) for index in road[:2]) or
                road[0] == road[1] or nodes[road[0]][:2] == nodes[road[1]][:2] or road[2] not in (0, 1)):
            raise ValueError('Cada estrada deve ligar dois pontos válidos e indicar se é de mão única.')
    if 'alerts' in data:
        data['alerts'] = import_points(data['alerts'])
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_MAP_BYTES:
        raise ValueError('Mapa maior que 32 MB.')
    return name[:80], payload


class Telemetry:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest = None
        self.received = 0
        self.map_payload = None
        self.map_revision = 0
        self.alert_scope = 'default'
        self.map_alerts = []

    def listen(self, source, stopped):
        with source:
            while not stopped.is_set():
                try:
                    payload, _ = source.recvfrom(8192)
                except socket.timeout:
                    continue
                data = decode(payload)
                if data is not None:
                    with self.lock:
                        self.latest, self.received = data, time.monotonic()

    def snapshot(self):
        with self.lock:
            return self.latest if time.monotonic() - self.received < 3 else None

    def set_map(self, payload):
        scope = hashlib.sha256(payload).hexdigest() if payload is not None else 'default'
        points = json.loads(payload).get('alerts', []) if payload is not None else []
        with self.lock:
            self.map_payload = payload
            self.map_revision += 1
            self.alert_scope, self.map_alerts = scope, points

    def map_state(self):
        with self.lock:
            return self.map_revision, self.map_payload

    def alert_map(self):
        with self.lock:
            return self.alert_scope, self.map_alerts


class PcVoice:
    LOCAL_VOICE = 'Faber · Português (Brasil)'
    LOCAL_MODEL = 'pt_BR-faber-medium.onnx'
    SYNTHESIZE = """$d = [Console]::In.ReadToEnd() | ConvertFrom-Json
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$m = New-Object System.IO.MemoryStream
try {
  $available = @($s.GetInstalledVoices() | Where-Object Enabled)
  if (!$available) { throw 'Nenhuma voz instalada no Windows.' }
  $v = $available | Where-Object { $_.VoiceInfo.Name -eq $d.voice } | Select-Object -First 1
  if (!$v) { $v = $available | Where-Object { $_.VoiceInfo.Culture.Name -eq 'pt-BR' } | Select-Object -First 1 }
  if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
  $s.Rate = [int][Math]::Round(($d.rate - 1) * 10)
  $s.SetOutputToWaveStream($m)
  $s.Speak([string]$d.text)
  $s.SetOutputToNull()
  [Console]::Write([Convert]::ToBase64String($m.ToArray()))
} finally { $s.Dispose(); $m.Dispose() }"""

    def __init__(self):
        root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'dist' / 'MaxHub'
        self.piper = root / 'voice'
        self.requests = queue.Queue(maxsize=2)
        self.synthesis_lock = threading.Lock()
        self.playback_lock = threading.Lock()
        self.status = ''
        threading.Thread(target=self._speak, daemon=True).start()

    @staticmethod
    def _command(script, data=None):
        command = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) /
                      'System32/WindowsPowerShell/v1.0/powershell.exe')
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        return subprocess.run([command, '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                              input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=12,
                              check=True)

    def voices(self):
        script = """[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    @($s.GetInstalledVoices() | Where-Object Enabled | ForEach-Object {$_.VoiceInfo.Name}) | ConvertTo-Json -Compress
} finally { $s.Dispose() }"""
        try:
            data = json.loads(self._command(script).stdout.decode('utf-8-sig'))
        except (OSError, ValueError, subprocess.SubprocessError):
            data = []
        installed = [data] if isinstance(data, str) else data if isinstance(data, list) else []
        return ([self.LOCAL_VOICE] if self.has_local_voice() else []) + installed

    def has_local_voice(self):
        return all((self.piper / name).is_file()
                   for name in ('piper.exe', self.LOCAL_MODEL, self.LOCAL_MODEL + '.json'))

    def synthesize_local(self, data):
        with tempfile.TemporaryDirectory(prefix='maxgps-voice-') as directory:
            output = Path(directory) / 'voice.wav'
            subprocess.run(
                [str(self.piper / 'piper.exe'), '--model', str(self.piper / self.LOCAL_MODEL),
                 '--length_scale', str(1 / data['rate']), '--output_file', str(output)],
                cwd=self.piper, input=(data['text'] + '\n').encode('utf-8'),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=15,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            return output.read_bytes()

    @staticmethod
    def payload(data):
        if not isinstance(data, dict):
            return None
        phrase, voice, rate = data.get('text'), data.get('voice', ''), data.get('rate', 1)
        if (not isinstance(phrase, str) or not 1 <= len(phrase.strip()) <= 180 or
                not isinstance(voice, str) or len(voice) > 160 or not number(rate) or not .6 <= rate <= 1.5):
            return None
        return json.dumps({'text': phrase.strip(), 'voice': voice, 'rate': rate}).encode('ascii')

    def submit(self, data):
        payload = self.payload(data)
        if payload is None:
            return False
        try:
            self.requests.put_nowait(payload)
            return True
        except queue.Full:
            return False

    def synthesize(self, payload):
        if not self.synthesis_lock.acquire(timeout=3):
            raise RuntimeError('O sintetizador do PC está ocupado. Tente novamente.')
        try:
            data = json.loads(payload)
            use_local = self.has_local_voice() and data['voice'] in ('', self.LOCAL_VOICE)
            try:
                wav = (self.synthesize_local(data) if use_local else
                       base64.b64decode(self._command(self.SYNTHESIZE, payload).stdout.strip(), validate=True))
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                if use_local:
                    raise RuntimeError('A voz integrada falhou. Reinstale o Max Hub para restaurar os arquivos de voz.') from exc
                if not self.has_local_voice():
                    raise RuntimeError('Nenhuma voz está disponível. Instale o Max Hub com a voz integrada.') from exc
                try:
                    wav = self.synthesize_local(data)
                except (OSError, ValueError, subprocess.SubprocessError) as local_error:
                    raise RuntimeError('A voz integrada falhou. Reinstale o Max Hub para restaurar os arquivos de voz.') from local_error
            try:
                if len(wav) < 100 or not wav.startswith(b'RIFF') or wav[8:12] != b'WAVE':
                    raise ValueError('Áudio inválido')
                return wav
            except ValueError as exc:
                raise RuntimeError('O sintetizador retornou áudio inválido.') from exc
        finally:
            self.synthesis_lock.release()

    def play(self, payload):
        if not self.playback_lock.acquire(timeout=3):
            raise RuntimeError('Já há um aviso tocando no PC.')
        try:
            wav = self.synthesize(payload)
            try:
                import winsound
                winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except (ImportError, RuntimeError) as exc:
                raise RuntimeError('O PC gerou a voz, mas a saída de áudio do Windows não reproduziu.') from exc
            self.status = 'Áudio reproduzido no computador.'
            return self.status
        except RuntimeError as exc:
            self.status = str(exc)
            raise
        finally:
            self.playback_lock.release()

    def _speak(self):
        while True:
            payload = self.requests.get()
            try:
                self.play(payload)
            except RuntimeError:
                continue

def make_handler(telemetry, token, voice, voices, media, alerts, pairing, features, commercial):
    files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
             '/style.css': ('style.css', 'text/css'), '/media.js': ('media.js', 'text/javascript')}
    assets = {route: ((ASSETS / filename).read_bytes(), media + '; charset=utf-8')
              for route, (filename, media) in files.items()}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()

        def allowed(self, target):
            key = self.headers.get('X-MaxGPS-Key') or parse_qs(target.query).get('chave', [''])[0]
            if hmac.compare_digest(key.encode('utf-8'), token.encode('ascii')):
                return True
            self.send_error(403, 'Use o endereco do Max Hub')
            return False

        def reply(self, payload, media='application/json', status=200):
            self.send_response(status)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def product_allowed(self, feature, enabled):
            if feature in enabled:
                return True
            self.reply(b'{"ok":false,"notice":"Ative este produto com a chave no Max Hub."}', status=403)
            return False

        def do_GET(self):
            target = urlsplit(self.path)
            if target.path in assets:
                self.reply(*assets[target.path])
                return
            if not self.allowed(target):
                return
            enabled = features()
            if target.path in ('/mapa', '/vozes', '/alertas') and not self.product_allowed('gps', enabled):
                return
            if target.path == '/multimidia' and not self.product_allowed('media', enabled):
                return
            if target.path == '/telemetria':
                gps = 'gps' in enabled
                version, _ = telemetry.map_state() if gps else (0, None)
                data = {'truck': telemetry.snapshot() if gps else None, 'mapRevision': version,
                        'alertRevision': alerts.revision if gps else 0,
                        'mapScope': telemetry.alert_map()[0] if gps else 'default',
                        'features': {product: product in enabled for product in ('track', 'gps', 'media')},
                        'releaseMode': 'commercial' if commercial else 'development'}
            elif target.path == '/mapa':
                _, payload = telemetry.map_state()
                self.reply(payload or b'null')
                return
            elif target.path == '/vozes':
                data = {'voices': list(voices), 'status': voice.status}
            elif target.path == '/multimidia':
                data = media.snapshot()
            elif target.path == '/alertas':
                data = alerts.snapshot(*telemetry.alert_map())
            else:
                self.send_error(404)
                return
            self.reply(json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8'))

        def do_POST(self):
            target = urlsplit(self.path)
            if target.path != '/parear' and not self.allowed(target):
                return
            if target.path not in ('/voz', '/voz/teste', '/voz/audio', '/multimidia', '/alertas', '/parear'):
                self.send_error(404)
                return
            if target.path != '/parear':
                feature = 'media' if target.path == '/multimidia' else 'gps'
                if not self.product_allowed(feature, features()):
                    return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 4096:
                    raise ValueError
                data = json.loads(self.rfile.read(length))
            except (ValueError, RecursionError):
                self.send_error(400)
                return
            if target.path == '/parear':
                device = pairing.pair(self.client_address[0], data)
                if device is None:
                    self.send_error(403, 'Codigo incorreto ou muitas tentativas')
                else:
                    self.reply(json.dumps(device).encode('utf-8'))
                return
            if target.path in ('/multimidia', '/alertas'):
                if target.path == '/multimidia':
                    ok, notice = media.perform(data)
                else:
                    scope, _ = telemetry.alert_map()
                    ok, notice = alerts.change(scope, data, telemetry.snapshot())
                self.reply(json.dumps({'ok': ok, 'notice': notice}).encode('utf-8'))
                return
            if target.path in ('/voz/teste', '/voz/audio'):
                payload = voice.payload(data)
                if payload is None:
                    self.send_error(400, 'Frase invalida')
                    return
                try:
                    if target.path == '/voz/audio':
                        self.reply(voice.synthesize(payload), 'audio/wav')
                    else:
                        notice = voice.play(payload)
                        self.reply(json.dumps({'ok': True, 'notice': notice}).encode('utf-8'))
                except RuntimeError as exc:
                    self.reply(json.dumps({'ok': False, 'notice': str(exc)}).encode('utf-8'), status=503)
                return
            if not voice.submit(data):
                self.send_error(429)
                return
            self.reply(b'{"ok":true}', status=202)

        def log_message(self, *_):
            pass

    return Handler


class Service:
    def __init__(self, address='0.0.0.0', port=8765, token=None, youtube_key='', alert_path=None,
                 features=None, commercial=False):
        self.telemetry = Telemetry()
        self.token = token or secrets.token_urlsafe(16)
        self.stopped = threading.Event()
        self.voice_names = []
        self.media = Media(youtube_key)
        self.alerts = RoadAlerts(alert_path)
        self.voice = PcVoice()
        self.pairing = LocalPairing(self.token)
        with_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with_socket.bind(('127.0.0.1', 4244))
            with_socket.settimeout(.5)
            self.http = ThreadingHTTPServer((address, port),
                make_handler(self.telemetry, self.token, self.voice, self.voice_names, self.media, self.alerts,
                             self.pairing, features or (lambda: {'track', 'gps', 'media'}), commercial))
        except Exception:
            with_socket.close()
            raise
        threading.Thread(target=self.telemetry.listen, args=(with_socket, self.stopped), daemon=True).start()
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        threading.Thread(target=lambda: self.voice_names.extend(self.voice.voices()), daemon=True).start()
        self.pairing.open(address, self.http.server_port, self.stopped)

    def url(self, address):
        return f'http://{address}:{self.http.server_port}/?chave={self.token}'

    def close(self):
        self.stopped.set()
        self.http.shutdown()
        self.http.server_close()


def lan_addresses():
    addresses = set()
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(('192.0.2.1', 9))
            addresses.add(probe.getsockname()[0])
        except OSError:
            pass
    private = tuple(map(ipaddress.IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
    return sorted(address for address in addresses if any(ipaddress.IPv4Address(address) in network for network in private))


def main():
    parser = argparse.ArgumentParser(description='Max GPS')
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    service = Service(args.bind, args.port)
    try:
        for address in [*lan_addresses(), '127.0.0.1'] if args.bind == '0.0.0.0' else [args.bind]:
            print(service.url(address), flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == '__main__':
    main()
