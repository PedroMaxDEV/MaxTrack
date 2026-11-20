"""Exercise the Hub API, map import and expiry over loopback."""
import json
from pathlib import Path
import socket
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from hub.server import Service, read_map
from hub.road_alerts import RoadAlerts


def main():
    service = Service('127.0.0.1', 0)
    base = f'http://127.0.0.1:{service.http.server_port}'
    key = f'?chave={service.token}'

    def read(path, auth=True):
        with urlopen(base + path + (key if auth else ''), timeout=3) as response:
            return response.read()

    try:
        assert b'Max GPS' in read('/')
        assert json.loads(read('/telemetria'))['truck'] is None
        for path in ('/telemetria', '/mapa', '/vozes', '/multimidia'):
            try:
                read(path, auth=False)
            except HTTPError as error:
                assert error.code == 403
            else:
                raise AssertionError(f'{path} accessible without pairing')
        def command(data, auth=True, path='/multimidia'):
            url = base + path + (key if auth else '')
            with urlopen(Request(url, data=json.dumps(data).encode()), timeout=3) as response:
                return json.load(response)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery:
            discovery.settimeout(2)
            discovery.sendto(b'MAXGPS/1 0123456789abcdef', ('127.0.0.1', 8766))
            info = json.loads(discovery.recv(512))
            assert info['service'] == 'MaxHub' and info['port'] == service.http.server_port
            assert info['nonce'] == '0123456789abcdef' and 'token' not in info and 'code' not in info
        paired = command({'code': service.pairing.code}, auth=False, path='/parear')
        assert paired['token'] == service.token
        try:
            wrong = '000000' if service.pairing.code != '000000' else '111111'
            command({'code': wrong}, auth=False, path='/parear')
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('Accepted incorrect pairing code')

        try:
            command({'action': 'expand'}, auth=False)
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('Remote command accepted without pairing')
        service.media.key = 'sample'
        sample_video = dict(id='abcdefghijk', title='Show ao vivo', channel='Teste')
        with patch('hub.media.youtube_results', return_value=[sample_video]) as lookup:
            assert command({'action': 'voice', 'phrase': 'Ok Max, abra o YouTube e coloque Natanzinho Lima'})['ok']
            lookup.assert_called_once_with('Natanzinho Lima', 'sample')
        assert service.media.actions.get_nowait() == ('apps', None)
        assert not command({'action': 'result', 'index': 1, 'query': 'Busca anterior'})['ok']
        assert command({'action': 'voice', 'phrase': 'Coloca o primeiro'})['ok']
        assert service.media.actions.get_nowait() == ('open', 'https://www.youtube.com/watch?v=abcdefghijk')

        sample = dict(speed=20, distance=12000, seconds=900, limit=22, x=1500, z=3400, heading=.25,
                      fuel=420, gear=11, delivery='São Paulo', paused=False)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.sendto(json.dumps(sample).encode(), ('127.0.0.1', 4244))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if json.loads(read('/telemetria'))['truck'] == sample:
                break
            time.sleep(.05)
        else:
            raise AssertionError('Telemetry did not reach the dashboard')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'map.json'
            graph = dict(version=1, name='Teste com mão única', nodes=[[0,0],[0,100],[100,100]],
                         roads=[[0,1,0],[1,2,1]], alerts=[dict(type='bump', x=0, z=30)])
            path.write_text(json.dumps(graph), encoding='utf-8')
            name, payload = read_map(path)
            assert name == graph['name']
            service.telemetry.set_map(payload)
            assert json.loads(read('/mapa')) == graph
            assert json.loads(read('/telemetria'))['mapRevision'] == 1
            marker_file = Path(folder) / 'markers.json'
            service.alerts.path = marker_file
            alerts = json.loads(read('/alertas'))
            scope = alerts['scope']
            assert alerts['points'] == [{'id': 'map-0', **graph['alerts'][0]}]
            marker = {'action': 'add', 'scope': scope, 'type': 'radar'}
            assert command(marker, path='/alertas')['ok']
            assert not command(marker, path='/alertas')['ok']
            assert not command({**marker, 'scope': 'default'}, path='/alertas')['ok']
            point = RoadAlerts(marker_file).snapshot(scope, [])['points'][0]
            assert (point['type'], point['x'], point['z'], point['heading']) == ('radar', 1500, 3400, .25)
            assert not command({'action': 'delete', 'scope': scope, 'id': 'map-0'}, path='/alertas')['ok']
            assert command({'action': 'delete', 'scope': scope, 'id': point['id']}, path='/alertas')['ok']
            assert not RoadAlerts(marker_file).snapshot(scope, [])['points']
            exported = {'nodes': [[0, 0], [0, 100], [100, 100]], 'edges': [[0, 1, 100, 2], [1, 2, 100, 1]]}
            export_file = Path(folder) / 'Mapa local.json'
            export_file.write_text(json.dumps(exported), encoding='utf-8')
            _, converted = read_map(export_file)
            assert json.loads(converted)['roads'] == [[0, 1, 1]]
            graph['roads'].append([9, 0, 0])
            path.write_text(json.dumps(graph), encoding='utf-8')
            try:
                read_map(path)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid roads passed validation')
        time.sleep(3.1)
        assert json.loads(read('/telemetria'))['truck'] is None
        print('PASS: pairing, multimídia, UDP, imported map, persistent road alerts and expiry')
    finally:
        service.close()


if __name__ == '__main__':
    main()
