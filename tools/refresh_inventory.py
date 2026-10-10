"""Refresh an extracted, locally rebuilt distribution's installer file inventory."""
from pathlib import Path
import argparse
import hashlib
import json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path)
args = parser.parse_args()
root = args.directory.resolve(strict=True)
target = root / 'compatibility.json'
if not target.is_file() or not (root / 'Setup.cmd').is_file():
    parser.error('Choose the extracted distribution root containing Setup.cmd and compatibility.json.')
value = json.loads(target.read_text(encoding='utf-8-sig'))
value['files'] = [
    {'path': path.relative_to(root).as_posix(),
     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for path in sorted(root.rglob('*')) if path.is_file() and path != target
]
target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Refreshed', len(value['files']), 'files in', target)
