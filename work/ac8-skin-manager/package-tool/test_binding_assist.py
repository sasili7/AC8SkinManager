import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import os
import unittest
from unittest.mock import patch

from binding_assist import BindingStore, BindingError, validate_profile, choices, suggestions, export_profile, read_profile, MOD
from i18n import messages


def sample():
    return {'schema_version': 1, 'kind': 'ac8-material-bindings', 'aircraft_id': 'PP0021_su57',
            'game_sha256': '51510e2a520565dbe81fb0d569e95cd4393077acaaa859371489b80b8128829f', 'native': True,
            'materials': [{'slot': n, 'material': 'MaterialInstanceConstant /Game/Test/M_Body.M_Body',
                           'parameters': [{'parameter': 'BaseColor', 'texture': '/Game/Aircraft/PP0021_su57/T_Body.T_Body'}]}
                          for n in (10, 13)]}


class BindingTests(unittest.TestCase):
    def test_groups_repeated_texture_slots_and_exact_matching_only(self):
        options = choices(validate_profile(sample()))
        self.assertEqual(options[0]['slots'], [10, 13])
        result = suggestions([{'asset': '/Game/Aircraft/PP0021_su57/T_Body'}, {'asset': '/Game/Other/T_Body'}], options)
        self.assertTrue(result[0]['matched']); self.assertFalse(result[1]['matched'])

    def test_rejects_wrong_aircraft_build_and_mod_baselines(self):
        for key, value in [('aircraft_id', '../evil'), ('game_sha256', 'wrong'), ('native', False)]:
            profile = sample(); profile[key] = value
            with self.assertRaises(BindingError): validate_profile(profile)
        with self.assertRaises(BindingError): validate_profile(sample(), 'PP0022_f16c')
        profile = sample(); profile['materials'][0]['parameters'][0]['texture'] = '/Game/AC8SkinManager/Skins/Mod'
        with self.assertRaises(BindingError): validate_profile(profile)

    def test_rejects_duplicate_and_invalid_slots_and_parameters(self):
        for slot in (-1, 128, True, 10):
            profile = sample(); profile['materials'][1]['slot'] = slot
            with self.assertRaises(BindingError): validate_profile(profile)
        profile = sample(); profile['materials'][0]['parameters'] *= 2
        with self.assertRaises(BindingError): validate_profile(profile)

    def test_unicode_store_export_and_bad_file_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = BindingStore(root / '中文记录')
            store.save(sample()); target = root / '分享材质.json'
            export_profile(store.load('PP0021_su57'), target)
            self.assertEqual(read_profile(target), validate_profile(sample()))
            captured = root / 'game' / MOD / 'BindingProfiles/PP0021_su57.json'
            captured.parent.mkdir(parents=True); captured.write_text('{bad')
            self.assertEqual(store.load('PP0021_su57', root / 'game'), validate_profile(sample()))
            with self.assertRaises(BindingError): read_profile(captured)
            self.assertFalse(list(target.parent.glob('.ac8-binding-*')))

    def test_capture_token_response_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = BindingStore(root / 'records'); mod = root / 'game' / MOD
            (mod / 'Scripts').mkdir(parents=True); (mod / 'Scripts/binding_capture.lua').touch()
            errors = []
            def respond():
                try:
                    deadline = time.monotonic() + 3
                    request = mod / 'binding-request.json'
                    while not request.exists():
                        if time.monotonic() > deadline: raise TimeoutError()
                        time.sleep(.01)
                    # Exclusive creation precedes JSON completion: tolerate partial writes.
                    while True:
                        try: data = json.loads(request.read_text()); break
                        except ValueError: time.sleep(.01)
                    (mod / 'binding-response.json').write_text(json.dumps({'token': data['token'], 'ok': True, 'profile': sample()}))
                except Exception as error: errors.append(error)
            thread = threading.Thread(target=respond); thread.start()
            with patch('compatibility.preflight'), patch('packaging_core.game_running', return_value=True):
                self.assertEqual(store.capture(root / 'game', 'PP0021_su57', 3)['aircraft_id'], 'PP0021_su57')
            thread.join(4); self.assertFalse(errors); self.assertFalse((mod / 'binding-request.json').exists())

    def test_timeout_does_not_accept_stale_reply_or_remove_other_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = BindingStore(root / 'records'); mod = root / 'game' / MOD
            (mod / 'Scripts').mkdir(parents=True); (mod / 'Scripts/binding_capture.lua').touch()
            (mod / 'binding-response.json').write_text(json.dumps({'token': 'stale', 'ok': True, 'profile': sample()}))
            with patch('compatibility.preflight'), patch('packaging_core.game_running', return_value=True):
                with self.assertRaisesRegex(BindingError, 'timed out'): store.capture(root / 'game', 'PP0021_su57', .1)
                request = mod / 'binding-request.json'; request.write_text('{"token":"other"}')
                with self.assertRaisesRegex(BindingError, 'pending'): store.capture(root / 'game', 'PP0021_su57', .1)
                self.assertEqual(request.read_text(), '{"token":"other"}')

    def test_refresh_keeps_imported_profile_until_new_game_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = BindingStore(root / 'records')
            captured = root / 'game' / MOD / 'BindingProfiles/PP0021_su57.json'
            captured.parent.mkdir(parents=True); captured.write_text(json.dumps(sample()))
            os.utime(captured, (1, 1))
            imported = sample(); imported['mesh'] = 'Imported profile'
            store.save(imported)
            self.assertEqual(store.load('PP0021_su57', root / 'game')['mesh'], 'Imported profile')
            refreshed = sample(); refreshed['mesh'] = 'New capture'
            captured.write_text(json.dumps(refreshed)); os.utime(captured, (time.time()+1, time.time()+1))
            self.assertEqual(store.load('PP0021_su57', root / 'game')['mesh'], 'New capture')

    def test_english_errors_are_translated(self):
        try: validate_profile({})
        except BindingError as error:
            self.assertEqual(messages(str(error))['en'], 'Invalid material binding profile.')


if __name__ == '__main__': unittest.main()
