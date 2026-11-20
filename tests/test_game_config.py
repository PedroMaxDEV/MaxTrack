import unittest
from game_config import prepare

class GameConfigTests(unittest.TestCase):
    def original(self):
        return '\r\n'.join(f'config_lines[{i}]: "mix {name} `old`"' for i,name in enumerate(
            ['trackiron','trackiryaw','trackirpitch','trackirroll','trackirx','trackiry','trackirz']))+'\r\nkeep steering and pedals'
    def test_preserves_other_controls(self):
        result=prepare(self.original(),'sdk.maxtrack.yaw','sdk.maxtrack.pitch')
        self.assertTrue(result.endswith('keep steering and pedals'))
        self.assertIn('(sdk.maxtrack.yaw?0) * 0.5',result)
        self.assertEqual(result.count('\r\n'),7)
    def test_refuses_ambiguous_profile(self):
        with self.assertRaises(ValueError): prepare('','sdk.maxtrack.yaw','sdk.maxtrack.pitch')
        with self.assertRaises(ValueError): prepare(self.original(),'bad`input','sdk.maxtrack.pitch')
