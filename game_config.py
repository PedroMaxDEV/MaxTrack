"""Reversible head-tracking bindings for the experimental SCS input bridge.

Only prepares text; callers must close the game and review before applying.
"""
import re
from pathlib import Path
import hashlib
import json

def prepare(text, yaw_input, pitch_input, yaw_scale=.5, pitch_scale=.25, depth=False, lateral=False):
    # Inputs must be copied from a binding written/identified by the game.
    for value in (yaw_input, pitch_input):
        if not re.fullmatch(r"sdk\.[a-z0-9_]+\.[a-z0-9_]+", value):
            raise ValueError('Identificador SDK inválido')
    replacements = {
        'trackiron': '1',
        'trackiryaw': f'({yaw_input}?0) * {yaw_scale:g}',
        'trackirpitch': f'({pitch_input}?0) * {pitch_scale:g}',
        'trackirroll': '0', 'trackirx': '0', 'trackiry': '0', 'trackirz': '0',
    }
    if depth:
        replacements['trackirz'] = 'sdk.maxtrack.z?0'
    if lateral:
        replacements['trackirx'] = 'sdk.maxtrack.x?0'
    for name, value in replacements.items():
        pattern = rf'(mix {name} `)[^`]*(`)'
        if len(re.findall(pattern,text)) != 1:
            raise ValueError(f'Mix ausente ou duplicado: {name}')
        text = re.sub(pattern, lambda match: match[1]+value+match[2], text)
    # Undo the exact wrapper written by earlier installers, keeping the original keys.
    for camera, button in (('cam5', 'window'), ('cam1', 'cabin')):
        pattern = rf'(mix {camera} `)\(([^\x60]*)\) \| sdk\.maxtrack\.{button}\?0(`)'
        text = re.sub(pattern, r'\1\2\3', text)
    return text

def stage(source, destination, yaw_input, pitch_input, depth=False):
    """Create a reviewable candidate and provenance without changing the profile."""
    original = source.read_bytes()
    candidate = prepare(original.decode('utf-8-sig'),yaw_input,pitch_input,depth=depth).encode('utf-8')
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'controls.original.sii').write_bytes(original)
    (destination/'controls.candidate.sii').write_bytes(candidate)
    (destination/'manifest.json').write_text(json.dumps({
        'source':str(source.resolve()),
        'original_sha256':hashlib.sha256(original).hexdigest(),
        'candidate_sha256':hashlib.sha256(candidate).hexdigest(),
        'status':'experimental; binding names and angular scale require in-game validation'
    },indent=2),encoding='utf-8')

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--yaw-input',required=True)
    parser.add_argument('--pitch-input',required=True)
    parser.add_argument('--depth',action='store_true')
    args=parser.parse_args()
    stage(args.source,args.destination,args.yaw_input,args.pitch_input,args.depth)
