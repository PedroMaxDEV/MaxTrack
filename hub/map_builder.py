"""Generate a Max GPS graph from the installed ETS2 and last mounted mods."""
import hashlib
import json
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
    old_paths = MOUNT.findall(log.read_text(encoding='utf-8-sig', errors='replace'))
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


def convert_graph(parsed, result, name):
    points = json.loads((parsed / 'europe-nodes.json').read_bytes())
    graph = json.loads((result / 'europe-graph.json').read_bytes())['graph']
    # The extractor reports the game's X/Z as x/y. Its z field is altitude.
    coordinates = {point['uid']: [round(point['x'], 2), round(point['y'], 2)] for point in points}
    del points
    directed = set()
    for uid, neighbors in graph:
        if uid not in coordinates:
            continue
        for edge in (*neighbors.get('forward', []), *neighbors.get('backward', [])):
            destination = edge['nodeUid']
            if not edge.get('isFerry') and destination in coordinates and coordinates[uid] != coordinates[destination]:
                directed.add((uid, destination))
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
    return {'version': 1, 'name': name, 'nodes': [coordinates[key] for key in keys], 'roads': roads}


def build(game, mods, cache, status, bundled_archive=None):
    if not (game / 'base_map.scs').is_file() or not (game / 'def.scs').is_file():
        raise ValueError('A pasta selecionada precisa conter os arquivos base_map.scs e def.scs do ETS2.')
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
            rejected = [line for line in diagnostics if ': no se pudo leer (' in line and '), se saltea' in line]
        if rejected:
            raise ValueError(f'O extrator não conseguiu ler um dos pacotes. Consulte {log} ou selecione os mods manualmente.')
        run_tool([node, tools / 'bin/generator.mjs', 'graph', '-m', 'europe', '-i', parsed, '-o', result],
                 log, tools, status, 'Montando a rede de vias e cruzamentos…')
        status('Preparando o mapa para baixar no celular…')
        graph = convert_graph(parsed, result, 'ETS2 · mods do perfil' if mods else 'ETS2 · jogo base')
    target = cache / 'Mapa do ETS2.json'
    write_atomic(target, json.dumps(graph, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    return target
