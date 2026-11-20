import json
from pathlib import Path
import tempfile
import unittest
from settings_store import validated, write_settings

class SettingsTests(unittest.TestCase):
    def test_invalid_values(self):
        defaults={'smoothing':.25,'port':4242,'invert_x':True}
        self.assertEqual(validated({'smoothing':float('nan'),'port':-10,'invert_x':'false'},defaults),
                         {'smoothing':.25,'port':1,'invert_x':True})
        self.assertEqual(validated([],defaults),defaults)

    def test_profiles_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            profiles={'ETS2':{'smoothing':.25},'ATS':{'smoothing':.6}}
            write_settings(path,{'invert_x':False},profiles,'ATS')
            value=json.loads(path.read_text())
            self.assertEqual(value['profiles'],profiles)
            self.assertEqual(value['active_profile'],'ATS')
            self.assertFalse(value['invert_x'])
            self.assertFalse(path.with_suffix('.tmp').exists())
