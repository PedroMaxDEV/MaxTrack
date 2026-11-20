"""Collect installed distribution metadata and notices for review, not legal clearance."""
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

def collect(destination):
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get('Name', 'unknown')
        inventory.append({'name': name, 'version': distribution.version,
                          'license': distribution.metadata.get('License'),
                          'license_expression': distribution.metadata.get('License-Expression')})
        for entry in distribution.files or []:
            if any(word in entry.name.lower() for word in ('license', 'notice', 'copying')):
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    target = destination / name / str(entry).replace('..', '_parent')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (destination / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    runtime=Path(sys.base_prefix)
    for source in [runtime/'LICENSE.txt', *list((runtime/'tcl').rglob('license.terms'))]:
        if source.is_file():
            target=destination/'Python-Tcl-Tk'/source.relative_to(runtime)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)

if __name__ == '__main__':
    collect(Path(sys.argv[1]) if len(sys.argv) > 1 else Path('dist/MaxTrackPro/THIRD_PARTY_NOTICES'))
