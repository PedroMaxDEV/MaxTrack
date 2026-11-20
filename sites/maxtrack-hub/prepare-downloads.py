import hashlib
import json
from pathlib import Path
from shutil import copyfile

root = Path(__file__).resolve().parents[2]
downloads = Path(__file__).resolve().parent / 'dist' / 'downloads'
downloads.mkdir(parents=True, exist_ok=True)
installer = root / 'dist' / 'installer' / 'MaxTrackPro-Setup.exe'
digest = hashlib.sha256()
parts = []
with installer.open('rb') as source:
    while chunk := source.read(16 * 1024 * 1024):
        name = f'MaxTrackPro-Setup.part{len(parts) + 1:02d}'
        (downloads / name).write_bytes(chunk)
        parts.append({'name': name, 'bytes': len(chunk)})
        digest.update(chunk)
(downloads / 'installer.json').write_text(json.dumps({
    'bytes': installer.stat().st_size, 'sha256': digest.hexdigest(), 'parts': parts
}), encoding='utf-8')
(downloads / installer.name).unlink(missing_ok=True)
copyfile(root / 'dist' / 'MaxTrackHub-Preview.zip', downloads / 'MaxTrackHub-Preview.zip')
