import json
import tempfile
import unittest
from pathlib import Path

from hub.map_builder import active_mods, build, convert_graph, lane_connections
from hub.server import read_map


class GpsMaps(unittest.TestCase):
    def test_external_roads_keep_direction_and_curve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {
                "nodes": [dict(uid="a", x=0, y=0, rotation=1), dict(uid="b", x=300, y=0, rotation=-1)],
                "roads": [dict(startNodeUid="a", endNodeUid="b", roadLookToken="local")],
                "roadLooks": [dict(token="local", lanesLeft=[], lanesRight=["local"])],
                "prefabs": [], "prefabDescriptions": [],
                "pois": [dict(type="facility", icon="gas_ico", x=40, y=5)],
            }
            for group, items in data.items():
                (root / f"europe-{group}.json").write_text(json.dumps(items))
            graph = convert_graph(root, None, "Externo")
            self.assertGreater(len(graph["nodes"]), 2)
            self.assertTrue(any(z > 0 for x, z in graph["nodes"]))
            self.assertTrue(all(direction == 1 for _, _, direction in graph["roads"]))
            self.assertEqual(graph["places"], [dict(type="fuel", x=40, z=5)])
            path = root / "map.json"
            path.write_text(json.dumps(graph))
            self.assertEqual(json.loads(read_map(path)[1]), graph)

    def test_prefab_exit_follows_only_connected_lanes(self):
        def curve(y, links):
            return dict(start=dict(x=0, y=y), end=dict(x=1, y=y), nextLines=links)
        prefab = dict(navCurves=[curve(0, [2]), curve(2, [3]), curve(0, []), curve(2, [])],
                      nodes=[dict(inputLanes=[1, 0], outputLanes=[]),
                             dict(inputLanes=[], outputLanes=[2]), dict(inputLanes=[], outputLanes=[3])])
        self.assertEqual(set(lane_connections(prefab)), {(0, 1, 2, 1), (0, 2, 2, 2)})

    def test_profile_switch_and_unsupported_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("base_map.scs", "def.scs", "one.scs", "two.scs"):
                (root / name).touch()
            log = root / "game.log.txt"
            log.write_text(f"[mods] Active 1 mod\n[fs] device {root/'one.scs'} mounted to mod pool.\n"
                           f"[mods] Active 1 mod\n[fs] device {root/'two.scs'} mounted to mod pool.\n")
            mods, missing = active_mods(root, root)
            self.assertEqual((mods, missing), ([root / "two.scs"], []))
            with self.assertRaisesRegex(ValueError, "two.scs"):
                build(root, mods, root, lambda _: None)
