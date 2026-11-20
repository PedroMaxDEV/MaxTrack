"""Generate a Max GPS graph from the installed ETS2 and last mounted mods."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile

from ets2_install import write_atomic

BUILDER = '1.5.43'
ZIP_HASH = '0c7a22c60257408273d0016331e3e66554909c00bc57011335b6b098b7603913'
ZIP_URL = ('https://github.com/Nethercap/truck-companion/releases/download/v1.5.43/'
           'TruckDash-MapBuilder-1.5.43.zip')
MOUNT = re.compile(r'\[fs\] device (.+?) mounted to mod pool\.', re.IGNORECASE)
WORKSHOP = re.compile(r'/workshop/content/227300/(\d+)/(.+)$', re.IGNORECASE)


def active_mods(documents_game, game):
    log = documents_game / 'game.log.txt'
    if not log.is_file():
        return [], []
    content = log.read_text(encoding='utf-8-sig', errors='replace')
    sessions = list(re.finditer(r'\[mods\] Active (\d+) mods?\b', content, re.IGNORECASE))
    if sessions:
        content = content[sessions[-1].end():]
    old_paths = MOUNT.findall(content)
    workshop = game.parent.parent / 'workshop/content/227300'
    mounted, missing = [], []
    for old in old_paths:
        path = Path(old)
        if not path.exists():
            normalized = old.replace('\\', '/')
            match = WORKSHOP.search(normalized)
            parts = Path(match[2]).parts if match else ()
            if match and not Path(match[2]).anchor and '..' not in parts:
                path = workshop / match[1] / match[2]
            else:
                path = documents_game / 'mod' / path.name
        if path.exists():
            mounted.append(path.resolve())
        else:
            missing.append(Path(old).name)
    if sessions and len(set(old_paths)) < int(sessions[-1][1]):
        missing.append('O log ainda não contém todos os pacotes do perfil.')
    return list(dict.fromkeys(mounted)), list(dict.fromkeys(missing))


def prepare_tools(cache, status, bundled_archive=None):
    root = cache / ('builder-' + BUILDER)
    required = ('node.exe', 'bin/parser.mjs', 'bin/generator.mjs')
    if all((root / file).is_file() for file in required):
        return root
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='download-') as temp:
        folder = Path(temp)
        if bundled_archive is not None and bundled_archive.is_file():
            archive = bundled_archive
            status('Preparando o extrator incluído no Hub…')
        else:
            status('Baixando o extrator de mapas (36 MB)…')
            archive = folder / 'builder.zip'
            request = Request(ZIP_URL, headers={'User-Agent': 'MaxHub/0.3.3'})
            with urlopen(request, timeout=30) as source, archive.open('wb') as target:
                for block in iter(lambda: source.read(256 * 1024), b''):
                    if target.tell() + len(block) > 40_000_000:
                        raise ValueError('O pacote do extrator excedeu o tamanho esperado.')
                    target.write(block)
        with archive.open('rb') as contents:
            digest = hashlib.file_digest(contents, 'sha256').hexdigest()
        if digest != ZIP_HASH:
            raise ValueError('A verificação SHA-256 do extrator falhou.')
        try:
            with ZipFile(archive) as bundle:
                bundle.extractall(folder)
        except BadZipFile as exc:
            raise ValueError('O pacote do extrator está danificado.') from exc
        extracted = folder / 'truckdash-map-builder'
        if not all((extracted / file).is_file() for file in required):
            raise ValueError('O pacote do extrator está incompleto.')
        if root.exists():
            raise ValueError('O extrator local está incompleto. Remova sua pasta de cache e tente novamente.')
        extracted.replace(root)
    return root


def run_tool(command, log, cwd, status, message):
    status(message)
    env = dict(os.environ, NODE_OPTIONS='--max-old-space-size=4096')
    with log.open('ab') as output:
        result = subprocess.run([str(part) for part in command], cwd=cwd, stdout=output,
                                stderr=subprocess.STDOUT, env=env, timeout=600,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode != 0:
        raise ValueError(f'O extrator falhou nesta etapa. Consulte o log em {log}.')


def parsed_items(folder, group):
    return json.loads((folder / f'europe-{group}.json').read_bytes())


def lane_connections(description):
    """Resolve each incoming lane to the exits reachable along its nav curves."""
    curves = description['navCurves']
    exits = {curve: index for index, node in enumerate(description['nodes'])
             for curve in node['outputLanes']}
    for origin, node in enumerate(description['nodes']):
        inputs = node['inputLanes']
        if not inputs:
            continue
        first = curves[inputs[0]]
        dx = first['end']['x'] - first['start']['x']
        dz = first['end']['y'] - first['start']['y']
        ordered = sorted(inputs, key=lambda index: dx * curves[index]['start']['y']
                         - dz * curves[index]['start']['x'])
        by_exit = {}
        for lane, start in enumerate(ordered):
            pending, visited = [start], set()
            while pending:
                index = pending.pop()
                if index in visited:
                    continue
                visited.add(index)
                if index in exits:
                    dest = exits[index]
                    by_exit[dest] = by_exit.get(dest, 0) | (1 << lane)
                pending.extend(curves[index]['nextLines'])
        for dest, mask in by_exit.items():
            if origin != dest:
                yield origin, dest, len(inputs), mask


def convert_graph(parsed, result, name):
    points = parsed_items(parsed, 'nodes')
    coordinates = {point['uid']: [round(point['x'], 2), round(point['y'], 2)] for point in points}
    rotation = {point['uid']: point['rotation'] for point in points}
    del points
    road_items = parsed_items(parsed, 'roads')
    directed, lanes = set(), {}
    if result is not None:
        graph = json.loads((result / 'europe-graph.json').read_bytes())['graph']
        for uid, neighbors in graph:
            for edge in (*neighbors.get('forward', []), *neighbors.get('backward', [])):
                if not edge.get('isFerry'):
                    directed.add((uid, edge['nodeUid']))
    else:
        looks = {look['token']: look for look in parsed_items(parsed, 'roadLooks')}
        for road in road_items:
            look = looks.get(road['roadLookToken'])
            if look:
                a, b = road['startNodeUid'], road['endNodeUid']
                if look['lanesRight']:
                    directed.add((a, b))
                if look['lanesLeft']:
                    directed.add((b, a))
    templates = {d['token']: list(lane_connections(d)) for d in parsed_items(parsed, 'prefabDescriptions')}
    for prefab in parsed_items(parsed, 'prefabs'):
        nodes = prefab['nodeUids']
        offset = prefab['originNodeIndex']
        nodes = nodes[-offset:] + nodes[:-offset]
        for start, end, count, mask in templates.get(prefab['token'], ()):
            if max(start, end) >= len(nodes):
                continue
            pair = nodes[start], nodes[end]
            if result is None:
                directed.add(pair)
            if 1 < count <= 8 and mask != (1 << count) - 1:
                lanes[pair] = count, mask
    directed = {(a, b) for a, b in directed if a in coordinates and b in coordinates
                and coordinates[a] != coordinates[b]}
    keys = sorted({node for pair in directed for node in pair})
    if not 2 <= len(keys) <= 200_000:
        raise ValueError('Mapa vazio ou acima do limite de nós desta versão.')
    indexes = {key: index for index, key in enumerate(keys)}
    roads = []
    for a, b in sorted(directed):
        reverse = (b, a) in directed
        if not reverse or a < b:
            roads.append([indexes[a], indexes[b], int(not reverse)])
    if len(roads) > 400_000:
        raise ValueError('O mapa excede o limite de vias desta versão.')
    # Sample road splines using the map's endpoint headings. Keep intersections
    # and direction unchanged, including when the v1 graph has little space left.
    positions = [coordinates[key] for key in keys]
    road_by_pair = {frozenset((r['startNodeUid'], r['endNodeUid'])): r for r in road_items}
    segments = []
    available = min(200_000 - len(keys), 400_000 - len(roads))
    for a, b, one_way in roads:
        road = road_by_pair.get(frozenset((keys[a], keys[b])))
        intermediate = []
        if road and available:
            start, end = road['startNodeUid'], road['endNodeUid']
            p, q = coordinates[start], coordinates[end]
            length = math.dist(p, q)
            steps = min(8, available + 1, max(1, math.ceil(length / 75)))
            tangents = [[length*math.cos(rotation[k]), length*math.sin(rotation[k])] for k in (start, end)]
            for part in range(1, steps):
                t = part / steps
                u = 1 - t
                point = [round((1+2*t)*u*u*p[k] + t*u*u*tangents[0][k]
                               + t*t*(3-2*t)*q[k] - t*t*u*tangents[1][k], 2) for k in (0, 1)]
                if point != p and point != q and (not intermediate or point != positions[intermediate[-1]]):
                    intermediate.append(len(positions))
                    positions.append(point)
            if keys[a] != start:
                intermediate.reverse()
            available -= len(intermediate)
        line = [a, *intermediate, b]
        segments.extend([first, second, one_way] for first, second in zip(line, line[1:]))
    places = []
    facilities = {'gas_ico': 'fuel', 'parking_ico': 'rest', 'service_ico': 'service'}
    poi_file = parsed / 'europe-pois.json'
    if poi_file.is_file():
        for point in json.loads(poi_file.read_bytes()):
            kind = facilities.get(point.get('icon')) if point.get('type') == 'facility' else None
            if point.get('type') == 'company' and point.get('cityToken') and point.get('icon'):
                kind = 'company'
            if kind:
                place = {'type': kind, 'x': round(point['x'], 2), 'z': round(point['y'], 2)}
                if kind == 'company':
                    place.update(city=point['cityToken'], company=point['icon'])
                places.append(place)
    hints = [[indexes[a], indexes[b], count, mask] for (a, b), (count, mask) in lanes.items()
             if (a, b) in directed]
    return {'lanes': hints, 'places': places, 'version': 1, 'name': name, 'nodes': positions, 'roads': segments}


def build(game, mods, cache, status, bundled_archive=None, expected_module=None):
    if not (game / 'base_map.scs').is_file() or not (game / 'def.scs').is_file():
        raise ValueError('A pasta selecionada precisa conter os arquivos base_map.scs e def.scs do ETS2.')
    unsupported = []
    for mod in mods:
        if mod.is_dir():
            continue
        with mod.open('rb') as source:
            magic = source.read(4)
        if magic not in (b'SCS#', b'AEM!') and not magic.startswith(b'PK'):
            unsupported.append(mod.name)
    if unsupported:
        raise ValueError('Formato de mod incompatível com o extrator: ' + ', '.join(unsupported)
                         + '. Importe um grafo JSON do autor pelo Hub.')
    tools = prepare_tools(cache, status, bundled_archive)
    node = tools / 'node.exe'
    log = cache / 'extracao.log'
    log.write_bytes(b'')
    with tempfile.TemporaryDirectory(dir=cache, prefix='build-') as tmp:
        work = Path(tmp)
        parsed, result = work / 'parsed', work / 'graph'
        parsed.mkdir()
        result.mkdir()
        listing = work / 'mods.txt'
        listing.write_text('\n'.join(map(str, mods)), encoding='utf-8')
        run_tool([node, tools / 'bin/parser.mjs', game, '@' + str(listing), parsed], log, tools,
                 status, f'Lendo o ETS2 e {len(mods)} pacote(s) do perfil…')
        with log.open(encoding='utf-8', errors='replace') as diagnostics:
            module = None
            for line in diagnostics:
                if 'se saltea' in line or 'skipping sector ' in line:
                    raise ValueError(f'O extrator ignorou dados do mapa. Consulte {log}.')
                match = re.search(r'parsing ([^/\s]+) sector files', line)
                if match:
                    module = match[1]
        if expected_module and (module or '').casefold() != expected_module.casefold():
            raise ValueError(f'O perfil carregou {expected_module}, mas o extrator leu {module or "um módulo desconhecido"}.')
        try:
            run_tool([node, tools / 'bin/generator.mjs', 'graph', '-m', 'europe', '-i', parsed, '-o', result],
                     log, tools, status, 'Montando a rede de vias e cruzamentos.')
        except ValueError:
            # Some standalone maps omit country tables or have isolated prefabs.
            # Keep only explicit road directions and connected prefab nav curves.
            result = None
            status('Construindo rotas com as vias e conversões identificadas no mapa externo.')
        status('Preparando o mapa para baixar no celular…')
        name = module or 'ETS2'
        if result is None:
            name += ' · vias identificadas'
        graph = convert_graph(parsed, result, name)
    target = cache / 'Mapa do ETS2.json'
    payload = json.dumps(graph, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    from hub.server import MAX_MAP_BYTES
    if len(payload) > MAX_MAP_BYTES:
        raise ValueError('O grafo excede o limite de 32 MB do Max GPS.')
    write_atomic(target, payload)
    return target
