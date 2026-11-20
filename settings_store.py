"""Backward-compatible settings validation and atomic persistence."""
import json
import math

LIMITS = {'camera': (0, 99), 'port': (1, 65535), 'sensitivity_x': (.3, 5),
          'sensitivity_y': (.3, 5), 'deadzone': (0, 6), 'smoothing': (0, .9),
          'max_yaw': (0, 180), 'max_pitch': (0, 90), 'anti_tremor': (0, 2)}
CAMERA_FPS_OPTIONS = (10, 15, 20, 25, 30)
PROFILE_KEYS = ('sensitivity_x', 'sensitivity_y', 'deadzone', 'smoothing',
                'lowlight', 'vertical', 'invert_x', 'invert_y', 'max_yaw', 'max_pitch', 'anti_tremor', 'responsive',
                'cabin_mode')

def validated(values, defaults):
    result = defaults.copy()
    if not isinstance(values, dict): return result
    for key, default in defaults.items():
        value = values.get(key, default)
        if key == 'camera_fps':
            if isinstance(value, int) and value in CAMERA_FPS_OPTIONS: result[key] = value
        elif isinstance(default, bool):
            if isinstance(value, bool): result[key] = value
        elif key in LIMITS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            lo, hi = LIMITS[key]
            result[key] = max(lo, min(hi, value))
            if isinstance(default, int): result[key] = int(result[key])
    return result

def write_settings(path, settings, profiles, active):
    payload = {**settings, 'profiles': profiles, 'active_profile': active}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)
