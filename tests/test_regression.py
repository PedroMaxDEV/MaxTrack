import ast
import math
from pathlib import Path
import socket
import struct
import unittest
import threading
from stabilization import stabilize

ROOT = Path(__file__).resolve().parents[1]

def functions(path):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}

class Regression(unittest.TestCase):
    def test_output_modes(self):
        nodes = functions(ROOT / 'maxtrack.py')
        send = next(n for n in nodes['App'].body if getattr(n, 'name', '') == 'send')
        scope = {'struct': struct, 'threading':threading, 'stabilize':stabilize}
        exec(compile(ast.Module(body=[nodes['packet'], send], type_ignores=[]), '<test>', 'exec'), scope)
        class Capture:
            def sendto(self, payload, address): self.payload, self.address = payload, address
        class Dummy: pass
        app = Dummy(); app.sock = Capture(); app.settings = {'port': 4242}
        scope['send'](app, 30, -10)
        self.assertEqual(app.sock.address, ('127.0.0.1', 4242))
        original = app.sock.payload
        app.settings['direct_bridge'] = True
        scope['send'](app, 30, -10)
        self.assertEqual(app.sock.address, ('127.0.0.1', 4243))
        self.assertEqual(app.sock.payload, original)
        scope['send'](app, 30, -10, -.1)
        self.assertEqual(struct.unpack('<6d',app.sock.payload)[2],-.1)
        scope['send'](app, 30, -10, -.1, .12)
        self.assertEqual(struct.unpack('<6d',app.sock.payload),(.12,0.,-.1,30.,-10.,0.))
        app.settings['direct_bridge'] = False
        scope['send'](app, 30, -10, -.1)
        self.assertEqual(app.sock.payload,original)
        app.settings['anti_tremor']=.6
        scope['send'](app,30.2,-10.2)
        self.assertEqual(app.sock.payload,original)
        scope['send'](app,0,0)
        self.assertEqual(struct.unpack('<6d',app.sock.payload),(0,0,0,0,0,0))

    def test_tracking_engine_unchanged(self):
        old = functions(ROOT / 'backups/original-0.9.8/maxtrack.py')
        new = functions(ROOT / 'maxtrack.py')
        for name in ('estimate_pose', 'fallback_pose', 'clamp', 'deadzone'):
            self.assertEqual(ast.dump(old[name]), ast.dump(new[name]), name)
        for name in ('toggle',):
            a = next(n for n in old['App'].body if getattr(n, 'name', '') == name)
            b = next(n for n in new['App'].body if getattr(n, 'name', '') == name)
            self.assertEqual(ast.dump(a), ast.dump(b), name)

    def test_udp_wire_contract(self):
        nodes = functions(ROOT / 'maxtrack.py')
        scope = {'struct': struct, 'math': math}
        exec(compile(ast.Module(body=[nodes[n] for n in ('packet', 'clamp', 'deadzone')], type_ignores=[]), '<test>', 'exec'), scope)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            receiver.bind(('127.0.0.1', 0)); receiver.settimeout(2)
            sender.sendto(scope['packet'](-25, 10), receiver.getsockname())
            data, _ = receiver.recvfrom(1024)
        self.assertEqual(len(data), 48)
        self.assertEqual(struct.unpack('<6d', data), (0, 0, 0, -25, 10, 0))
        self.assertAlmostEqual(scope['deadzone'](-2, .8), -1.2)
        self.assertEqual(scope['deadzone'](.5, .8), 0)
        self.assertEqual(scope['clamp'](100, -85, 85), 85)

if __name__ == '__main__': unittest.main()
