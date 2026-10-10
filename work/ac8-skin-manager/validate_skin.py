"""Author-facing manifest API v1 validator. Python 3.10+, standard library only."""
from pathlib import Path
import argparse
import json
import re
import sys


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ['Manifest must be a JSON object.']
    if data.get('schema_version') != 1 or isinstance(data.get('schema_version'), bool):
        errors.append('schema_version must be integer 1.')
    for field in ('provider_id', 'id'):
        if not isinstance(data.get(field), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', data[field]):
            errors.append(f'{field}: use 1-64 lowercase ASCII letters, digits, _ or -; start with a letter/digit.')
    plane = data.get('aircraft_id')
    if not isinstance(plane, str) or not re.fullmatch(r'PP[0-9]{4}_[a-z0-9]+', plane):
        errors.append('aircraft_id must be an exact cooked model token such as PP0021_su57.')
    title = data.get('name')
    if not isinstance(title, str) or not 0 < len(title.encode('utf-8')) <= 239:
        errors.append('name must contain 1-239 UTF-8 bytes.')
    if not isinstance(data.get('author'), str):
        errors.append('author must be a string.')
    button = data.get('button', {})
    if not isinstance(button, dict):
        errors.append('button must be an object.')
    else:
        if 'text' in button:
            short = button['text']
            def permitted(c):
                cp = ord(c)
                return ('A' <= c <= 'Z' or 'a' <= c <= 'z'
                        or 0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF
                        or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x2FA1F
                        or 0x30000 <= cp <= 0x323AF)
            if not isinstance(short, str) or not 1 <= len(short) <= 3 or not all(permitted(c) for c in short):
                errors.append('button.text must contain 1-3 English letters or Han characters (mixed text allowed).')
        for field in ('background_color', 'text_color'):
            if field in button and (not isinstance(button[field], str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', button[field])):
                errors.append(f'button.{field} must be #RRGGBB.')
    if data.get('status') not in ('draft', 'ready'):
        errors.append('status must be draft or ready.')
    bindings = data.get('bindings', [])
    if not isinstance(bindings, list):
        errors.append('bindings must be an array.')
        bindings = []
    if data.get('status') == 'ready' and not bindings:
        errors.append('ready skins require real material bindings.')
    prefix = f"/Game/AC8SkinManager/Skins/{data.get('provider_id')}/{plane}/{data.get('id')}/"
    seen = set()
    for i, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            errors.append(f'bindings[{i}] must be an object.')
            continue
        if binding.get('target') != 'body':
            errors.append(f'bindings[{i}].target: API v1 supports body only.')
        index = binding.get('material_index')
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index <= 127:
            errors.append(f'bindings[{i}].material_index must be integer 0-127.')
        parameter = binding.get('parameter')
        if not isinstance(parameter, str) or not 0 < len(parameter.encode('utf-8')) <= 120:
            errors.append(f'bindings[{i}].parameter must contain 1-120 UTF-8 bytes.')
        texture = binding.get('texture')
        if not isinstance(texture, str) or not texture.startswith(prefix) or len(texture) <= len(prefix) or '..' in texture or '\\' in texture:
            errors.append(f'bindings[{i}].texture must be inside {prefix}')
        key = (str(index), str(parameter))
        if key in seen:
            errors.append(f'bindings[{i}] duplicates a material slot/parameter.')
        seen.add(key)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        if args.manifest.stat().st_size > 262144:
            raise ValueError('skin.json exceeds 256KB.')
        data = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        errors = validate(data)
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print('\n'.join('ERROR: ' + error for error in errors))
        return 1
    print(f"OK: {data['provider_id']} / {data['aircraft_id']} / {data['id']} ({data['status']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
