"""Discovery and explicit pairing for the native Max GPS app."""
import hmac
import ipaddress
import json
import re
import secrets
import socket
import threading
import time

PORT = 8766
PRIVATE = tuple(map(ipaddress.IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
PROBE = re.compile(rb'MAXGPS/1 ([a-f0-9]{16})\Z')


def local_address(address):
    host = ipaddress.IPv4Address(address)
    return host.is_loopback or any(host in network for network in PRIVATE)


class LocalPairing:
    def __init__(self, token):
        self.token = token
        self.code = f'{secrets.randbelow(1_000_000):06d}'
        self.name = socket.gethostname()[:64]
        self.lock = threading.Lock()
        self.attempts = {}
        self.socket = None

    def open(self, address, http_port, stopped):
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            listener.settimeout(.5)
            listener.bind((address, PORT))
        except OSError:
            listener.close()
            return
        self.socket = listener
        threading.Thread(target=self.listen, args=(listener, http_port, stopped), daemon=True).start()

    def listen(self, listener, port, stopped):
        with listener:
            while not stopped.is_set():
                try:
                    payload, sender = listener.recvfrom(256)
                    match = PROBE.fullmatch(payload)
                    if match and local_address(sender[0]):
                        reply = json.dumps({'service':'MaxHub', 'name': self.name, 'port': port,
                                            'nonce':match[1].decode('ascii')}).encode('utf-8')
                        listener.sendto(reply, sender)
                except socket.timeout:
                    continue
                except OSError:
                    if stopped.is_set():
                        break

    def pair(self, address, data):
        if not local_address(address) or not isinstance(data, dict):
            return None
        code = data.get('code')
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
            return None
        now = time.monotonic()
        with self.lock:
            self.attempts = {host: entry for host, entry in self.attempts.items() if now-entry[0] < 60}
            if address not in self.attempts and len(self.attempts) >= 256:
                return None
            minute, count = self.attempts.get(address, (now, 0))
            if count >= 6:
                return None
            if hmac.compare_digest(code, self.code):
                self.attempts.pop(address, None)
                return {'token': self.token, 'name': self.name}
            self.attempts[address] = (minute, count+1)
            return None
