"""Map-specific road alert points for Max GPS."""
import json
import math
import re
import threading
import uuid

from ets2_install import write_atomic

TYPES = {'radar', 'police', 'bump'}
MAX_POINTS = 500
MAP_KEY = re.compile(r'(?:default|[a-f0-9]{64})\Z')


def coordinate(value):
    return type(value) in (int, float) and abs(value) < 10_000_000


def normalize(point):
    if not isinstance(point, dict) or not isinstance(point.get('type'), str) or point['type'] not in TYPES:
        raise ValueError('Tipo de alerta inválido.')
    if not all(coordinate(point.get(key)) for key in ('x', 'z')):
        raise ValueError('Alerta sem coordenadas X/Z válidas.')
    result = {key: point[key] for key in ('type', 'x', 'z')}
    heading = point.get('heading')
    if heading is not None:
        if not coordinate(heading) or not -1 <= heading <= 1:
            raise ValueError('A direção do alerta deve estar em voltas, entre -1 e 1.')
        result['heading'] = heading
    return result


def import_points(points):
    if not isinstance(points, list) or len(points) > MAX_POINTS:
        raise ValueError(f'O mapa pode incluir até {MAX_POINTS} alertas.')
    return [normalize(point) for point in points]


class RoadAlerts:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.Lock()
        self.saved = self.load()
        self.revision = 0

    def load(self):
        if not self.path:
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            result = {}
            for scope, points in raw.items():
                if not MAP_KEY.fullmatch(scope):
                    continue
                for point in points[:MAX_POINTS]:
                    identifier = point.get('id')
                    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
                        continue
                    result.setdefault(scope, []).append({'id': identifier, **normalize(point)})
            return result
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            return {}

    def snapshot(self, scope, imported):
        with self.lock:
            points = [{'id': f'map-{i}', **point} for i, point in enumerate(imported)]
            points.extend(self.saved.get(scope, ()))
            return {'scope': scope, 'revision': self.revision, 'points': points}

    def change(self, scope, command, truck):
        if not isinstance(command, dict) or command.get('scope') != scope:
            return False, 'O mapa mudou. Tente de novo.'
        with self.lock:
            points = self.saved.get(scope, [])
            if command.get('action') == 'add':
                kind = command.get('type')
                if not isinstance(kind, str) or kind not in TYPES:
                    return False, 'Escolha um tipo de alerta.'
                if not truck:
                    return False, 'Entre na cabine antes de marcar um alerta.'
                if len(points) >= MAX_POINTS:
                    return False, 'Limite de marcações atingido para este mapa.'
                try:
                    point = normalize({'type': kind, 'x': round(truck['x'], 2), 'z': round(truck['z'], 2),
                                       'heading': truck['heading'] % 1})
                except ValueError as exc:
                    return False, str(exc)
                if any(item['type'] == kind and math.hypot(item['x'] - point['x'], item['z'] - point['z']) < 18
                       and abs(math.remainder(item.get('heading', 0) - point['heading'], 1)) < .125 for item in points):
                    return False, 'Já existe um alerta deste tipo neste trecho e sentido.'
                updated = [*points, {'id': uuid.uuid4().hex, **point}]
            elif command.get('action') == 'delete':
                updated = [item for item in points if item['id'] != command.get('id')]
                if len(updated) == len(points):
                    return False, 'Marcação pessoal não encontrada.'
            else:
                return False, 'Comando inválido.'
            saved = self.saved.copy()
            if updated:
                saved[scope] = updated
            else:
                saved.pop(scope, None)
            try:
                if self.path:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    write_atomic(self.path, json.dumps(saved, ensure_ascii=False).encode('utf-8'))
            except OSError:
                return False, 'O Hub não conseguiu salvar a marcação.'
            self.saved = saved
            self.revision += 1
            return True, 'Marcação salva no PC.' if command['action'] == 'add' else 'Marcação removida.'
