"""Commercial configuration, Windows license storage and signed Hub updates."""
import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from ets2_install import write_atomic


PRODUCTS = frozenset({'track', 'gps', 'media'})
PRODUCT_NAMES = {'track': 'MaxTrack Pro', 'gps': 'Max GPS', 'media': 'Max Multimídia'}
MAX_INSTALLER_SIZE = 1024 * 1024 * 1024


class StoreError(RuntimeError):
    pass


class StoreResponseError(StoreError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4})){2}', value):
        raise StoreError('Versão inválida no catálogo de atualizações.')
    return tuple(map(int, value.split('.')))


def rsa_key(data):
    modulus, exponent = int(data['n'], 16), data['e']
    if (modulus.bit_length() not in (2048, 3072, 4096) or modulus % 2 == 0
            or type(exponent) is not int or not 3 <= exponent < 2**32 or exponent % 2 == 0):
        raise ValueError()
    return modulus, exponent


def check_release_config(data):
    try:
        origin = data['origin']
        url = urlsplit(origin)
        version = data['version']
        update_key = rsa_key(data['updateKey'])
        license_key = rsa_key(data['licenseKey'])
        version_tuple(version)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment or url.port not in (None, 443)
                or update_key == license_key):
            raise ValueError()
        return ReleaseConfig(origin, version, update_key, license_key)
    except (KeyError, TypeError, AttributeError, ValueError, StoreError) as exc:
        raise StoreError('A configuração comercial deste instalador está inválida.') from exc


@dataclass(frozen=True)
class ReleaseConfig:
    origin: str
    version: str
    update_key: tuple
    license_key: tuple


def release_config():
    if not getattr(sys, 'frozen', False):
        return None
    try:
        from max_release_config import SETTINGS
    except ImportError:
        pass
    else:
        return check_release_config(SETTINGS)
    config = Path(sys._MEIPASS) / 'hub' / 'store-config.json'
    if not config.exists():
        return None
    try:
        return check_release_config(json.loads(config.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError) as exc:
        raise StoreError('A configuração comercial deste instalador está inválida.') from exc


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def network_reason(error):
    reason = error.reason if isinstance(error, URLError) else error
    code = getattr(reason, 'winerror', None)
    if isinstance(error, HTTPError):
        return f'O site respondeu com HTTP {error.code}.'
    if isinstance(reason, ssl.SSLCertVerificationError) or code in (12037, 12038, 12045, 12057, 12175):
        return 'Falha ao verificar o certificado HTTPS. Confira a data e a hora do Windows.'
    if isinstance(reason, ssl.SSLError):
        return 'Não foi possível estabelecer a conexão HTTPS.'
    if isinstance(reason, socket.gaierror) or code == 12007:
        return 'Não foi possível localizar o endereço do site (DNS).'
    if isinstance(reason, TimeoutError) or code == 12002:
        return 'O site demorou para responder.'
    return 'O Windows não conseguiu conectar ao site. Confira o proxy e o firewall.'


def open_origin(config, path, payload=None, timeout=20):
    if not path.startswith('/') or path.startswith('//') or '\\' in path or '://' in path:
        raise StoreError('Caminho inválido.')
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    agent = f'MaxHub/{config.version}'

    def connect():
        if sys.platform == 'win32':
            from max_store_winhttp import open_https
            return open_https(config.origin, path, agent, body, timeout)
        request = Request(config.origin + path, data=body,
                          headers={'Content-Type': 'application/json', 'User-Agent': agent})
        return build_opener(NoRedirects()).open(request, timeout=timeout)

    try:
        return connect()
    except OSError as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        if (not isinstance(reason, (TimeoutError, ConnectionResetError, ConnectionAbortedError))
                and getattr(reason, 'winerror', None) not in (12002, 12030)):
            raise
    return connect()


def request_json(config, path, payload):
    try:
        with open_origin(config, path, payload) as response:
            reply = json.loads(response.read(32768))
    except HTTPError as exc:
        try:
            with exc:
                reply = json.loads(exc.read(4096))
            notice = reply.get('error', '')
        except (ValueError, AttributeError, OSError):
            notice = ''
        raise StoreResponseError(exc.code, notice[:160] if isinstance(notice, str) and notice
                                 else network_reason(exc)) from exc
    except OSError as exc:
        raise StoreError(f'Não foi possível consultar a loja. {network_reason(exc)}') from exc
    except ValueError as exc:
        raise StoreError('O site respondeu com dados de ativação inválidos.') from exc
    return reply


class DataBlob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def user_protection(data, encrypt):
    """Keep cached receipts bound to the current Windows account."""
    raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = DataBlob(len(data), raw), DataBlob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    protect = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    protect.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
    protect.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not protect(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def current_device():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography', 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            machine = winreg.QueryValueEx(key, 'MachineGuid')[0]
    except OSError:
        machine = str(uuid.getnode())
    return hashlib.sha256(('MaxHub:' + machine).encode('utf-8')).hexdigest()


def valid_receipt(data, config, device):
    if not isinstance(data, dict):
        return False
    token, products, expiry, proof = (data.get(name) for name in ('token', 'products', 'expiresAt', 'proof'))
    if (not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._-]{24,2048}', token)
            or not isinstance(products, list) or not 1 <= len(products) <= len(PRODUCTS)
            or not all(isinstance(p, str) and p in PRODUCTS for p in products) or len(set(products)) != len(products)
            or type(expiry) is not int or not 0 < expiry < 100_000_000_000
            or not isinstance(proof, str) or not proof.isascii() or len(proof) > 1024):
        return False
    statement = '\n'.join(('maxhub-lease-v1', config.origin, device, token,
                           ','.join(sorted(products)), str(expiry))).encode('utf-8')
    return valid_signature(config.license_key, statement, proof.encode('ascii'))


class Licenses:
    def __init__(self, config, data_dir):
        self.config = config
        self.path = data_dir / 'licenses.dpapi'
        self.operation = threading.Lock()
        self.cache_lock = threading.Lock()
        self.device = current_device() if config else ''
        self.receipts = self.load()

    def load(self):
        if not self.config:
            return {}
        try:
            data = json.loads(user_protection(self.path.read_bytes(), False))
            if data.get('origin') == self.config.origin and data.get('device') == self.device:
                return {key: receipt for key, receipt in data['receipts'].items()
                        if valid_receipt(receipt, self.config, self.device)}
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            pass
        return {}

    def active_products(self):
        if not self.config:
            return PRODUCTS
        with self.cache_lock:
            return {product for receipt in self.receipts.values() if receipt['expiresAt'] > time.time()
                    for product in receipt['products']}

    def allows(self, product):
        return product in self.active_products()

    def commit(self, receipts):
        payload = json.dumps({'origin': self.config.origin, 'device': self.device,
                              'receipts': receipts}).encode('utf-8')
        with self.cache_lock:
            self.receipts = receipts
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self.path, user_protection(payload, True))
        except OSError as exc:
            raise StoreError('A licença foi aplicada nesta sessão. O Windows não conseguiu salvar o acesso.') from exc

    def activate(self, key):
        key = key.strip().upper()
        if not re.fullmatch(r'[A-Z0-9-]{12,120}', key):
            raise StoreError('Confira o formato da chave de ativação.')
        with self.operation:
            receipt = request_json(self.config, '/api/activate', {'key': key, 'deviceId': self.device})
            if not valid_receipt(receipt, self.config, self.device) or receipt['expiresAt'] <= time.time():
                raise StoreError('A loja não retornou uma licença válida.')
            fingerprint = hashlib.sha256(key.encode('ascii')).hexdigest()
            self.commit({**self.receipts, fingerprint: receipt})

    def refresh(self):
        if not self.config:
            return
        with self.operation:
            receipts = self.receipts.copy()
            for identity, receipt in self.receipts.items():
                try:
                    updated = request_json(self.config, '/api/license/refresh',
                                           {'token': receipt['token'], 'deviceId': self.device})
                    if valid_receipt(updated, self.config, self.device):
                        receipts[identity] = updated
                except StoreResponseError as exc:
                    if exc.status in (401, 403, 404, 410):
                        receipts.pop(identity, None)
                except StoreError:
                    break
            if receipts != self.receipts:
                self.commit(receipts)


@dataclass(frozen=True)
class Release:
    version: str
    path: str
    digest: str
    size: int


def valid_signature(key, manifest, detached):
    try:
        signature = base64.b64decode(detached.strip(), validate=True)
    except ValueError:
        return False
    modulus, exponent = key
    width = (modulus.bit_length() + 7) // 8
    value = int.from_bytes(signature, 'big')
    if len(signature) != width or not 0 < value < modulus:
        return False
    # PKCS#1 v1.5 DigestInfo encoding for SHA-256.
    information = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(manifest).digest()
    expected = b'\x00\x01' + b'\xff' * (width - len(information) - 3) + b'\x00' + information
    actual = pow(value, exponent, modulus).to_bytes(width, 'big')
    return hmac.compare_digest(actual, expected)


def available_release(config):
    try:
        with open_origin(config, '/downloads/update.json') as response:
            manifest = response.read(8193)
        with open_origin(config, '/downloads/update.sig') as response:
            signature = response.read(4097)
    except OSError as exc:
        raise StoreError(f'Não foi possível consultar a atualização. {network_reason(exc)}') from exc
    if len(manifest) > 8192 or len(signature) > 4096 or not valid_signature(config.update_key, manifest, signature):
        raise StoreError('A assinatura da atualização não é válida.')
    try:
        data = json.loads(manifest)
        version, path, digest, size = (data[name] for name in ('version', 'path', 'sha256', 'size'))
        version_tuple(version)
        if (path != f'/downloads/releases/{version}/MaxHub-Setup.exe'
                or not re.fullmatch(r'[a-f0-9]{64}', digest)
                or type(size) is not int or not 1 <= size <= MAX_INSTALLER_SIZE):
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise StoreError('Os dados da atualização publicada estão inválidos.') from exc
    return Release(version, path, digest, size) if version_tuple(version) > version_tuple(config.version) else None


def download_release(config, release, folder, progress):
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder, prefix='download-') as working:
        partial = Path(working) / 'MaxHub-Setup.exe'
        digest = hashlib.sha256()
        received = 0
        try:
            with open_origin(config, release.path, timeout=45) as source, partial.open('wb') as output:
                for chunk in iter(lambda: source.read(512 * 1024), b''):
                    received += len(chunk)
                    if received > release.size:
                        raise StoreError('A atualização excedeu o tamanho assinado.')
                    digest.update(chunk)
                    output.write(chunk)
                    progress(100 * received // release.size)
        except OSError as exc:
            raise StoreError('O download da atualização foi interrompido. Tente novamente.') from exc
        if received != release.size or not hmac.compare_digest(digest.hexdigest(), release.digest):
            raise StoreError('A atualização baixada não corresponde à versão assinada.')
        installer = folder / f'MaxHub-{release.version}-Setup.exe'
        partial.replace(installer)
        return installer


def launch_update(installer, directory):
    subprocess.Popen([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                      '/CLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/MAXUPDATE=1',
                      f'/DIR={directory}', f'/LOG={installer.parent / "instalacao.log"}'],
                     cwd=installer.parent)
