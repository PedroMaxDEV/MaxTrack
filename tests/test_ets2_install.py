import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ets2_install


class SetupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.game = root / 'Game with spaces'
        game_bin = self.game / 'bin' / 'win_x64'
        game_bin.mkdir(parents=True)
        (game_bin / 'eurotrucks2.exe').touch()
        self.profile = root / 'controls.sii'
        self.profile.write_bytes(('\r\n'.join(f'mix trackir{axis} `0`' for axis in
                                  ('on','yaw','pitch','roll','x','y','z')) + '\r\nwheel-binding\r\n').encode())
        self.config = root / 'user' / 'config.json'
        self.config.parent.mkdir()
        self.config.write_text('{"profiles":{"ETS2":{"sensitivity_x":2.1},"ATS":{"sensitivity_x":1.7}}}')
        self.bridge = root / 'MaxTrackBridge.dll'
        self.bridge.write_bytes(b'dll')
        self.bridge.with_name('sdk_license.txt').write_text('license')
        self.plugin = game_bin / 'plugins' / self.bridge.name

    def test_configures_and_backs_up_the_selected_profile(self):
        original = self.profile.read_bytes()
        backup = ets2_install.configure(self.game, self.profile, self.config, self.bridge)
        self.assertEqual((backup / 'controls.sii').read_bytes(), original)
        self.assertIn(b'mix trackirz `sdk.maxtrack.z?0`\r\nwheel-binding\r\n', self.profile.read_bytes())
        self.assertIn(b'mix trackirx `sdk.maxtrack.x?0`\r\n', self.profile.read_bytes())
        self.assertEqual(self.plugin.read_bytes(), b'dll')
        settings = json.loads(self.config.read_bytes())
        self.assertTrue(settings['direct_bridge'])
        self.assertEqual(settings['sensitivity_x'], 2.1)
        self.assertEqual(settings['profiles']['ATS']['sensitivity_x'], 1.7)

    def test_rolls_back_plugin_when_profile_cannot_be_written(self):
        original = self.profile.read_bytes()
        write = ets2_install.write_atomic

        def locked_profile(path, contents):
            if path == self.profile:
                raise PermissionError('profile locked')
            write(path, contents)

        with patch.object(ets2_install, 'write_atomic', side_effect=locked_profile):
            with self.assertRaises(PermissionError):
                ets2_install.configure(self.game, self.profile, self.config, self.bridge)
        self.assertFalse(self.plugin.exists())
        self.assertEqual(self.profile.read_bytes(), original)

    def test_configures_all_profiles_with_separate_backups(self):
        documents = self.profile.parent / 'Euro Truck Simulator 2'
        profiles = [documents / folder / '4142' / 'controls.sii'
                    for folder in ('profiles', 'steam_profiles')]
        for index, profile in enumerate(profiles):
            profile.parent.mkdir(parents=True)
            camera = b'mix cam1 `keyboard.key1?0`\r\nmix cam5 `keyboard.key5?0 | joy.b5?0`\r\n'
            if index == 0:
                camera = (b'mix cam1 `(keyboard.key1?0) | sdk.maxtrack.cabin?0`\r\n'
                          b'mix cam5 `(keyboard.key5?0 | joy.b5?0) | sdk.maxtrack.window?0`\r\n')
            profile.write_bytes(self.profile.read_bytes() + camera + f'binding-{index}\r\n'.encode())
        game_settings = documents / 'config.cfg'
        game_settings.write_bytes(b'uset g_trackir "0"\r\nuset g_fps "1"\r\n')
        originals = [profile.read_bytes() for profile in profiles]
        count, backup = ets2_install.configure_profiles(self.game, documents, self.config, self.bridge)
        self.assertEqual(count, 2)
        self.assertEqual((backup / 'config.cfg').read_bytes(), b'uset g_trackir "0"\r\nuset g_fps "1"\r\n')
        self.assertEqual(game_settings.read_bytes(), b'uset g_trackir "1"\r\nuset g_fps "1"\r\n')
        for index, (profile, original) in enumerate(zip(profiles, originals)):
            self.assertEqual((backup / profile.relative_to(documents)).read_bytes(), original)
            self.assertIn(b'sdk.maxtrack.yaw', profile.read_bytes())
            self.assertIn(b'mix cam5 `keyboard.key5?0 | joy.b5?0`', profile.read_bytes())
            self.assertIn(b'mix cam1 `keyboard.key1?0`', profile.read_bytes())
            self.assertNotIn(b'sdk.maxtrack.window', profile.read_bytes())
            self.assertNotIn(b'sdk.maxtrack.cabin', profile.read_bytes())
            self.assertTrue(profile.read_bytes().endswith(f'binding-{index}\r\n'.encode()))

    def test_leaves_all_profiles_untouched_if_one_cannot_be_prepared(self):
        documents = self.profile.parent / 'Euro Truck Simulator 2'
        valid = documents / 'profiles' / '4142' / 'controls.sii'
        invalid = documents / 'steam_profiles' / '4344' / 'controls.sii'
        for profile in (valid, invalid):
            profile.parent.mkdir(parents=True)
        original = self.profile.read_bytes()
        valid.write_bytes(original)
        invalid.write_bytes(b'incomplete profile')
        with self.assertRaisesRegex(ValueError, '4344'):
            ets2_install.configure_profiles(self.game, documents, self.config, self.bridge)
        self.assertEqual(valid.read_bytes(), original)
        self.assertEqual(invalid.read_bytes(), b'incomplete profile')
        self.assertFalse(self.plugin.exists())
