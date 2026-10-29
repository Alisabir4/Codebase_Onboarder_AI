import unittest
from pathlib import PurePosixPath

from core.graph_builder import build_interactive_graph, resolve_local_dependencies, _json_safe
from core.analyzer import analyze_repository
import json


class BuildInteractiveGraphTests(unittest.TestCase):
    def test_pathlike_module_keys_generate_interactive_graph(self):
        modules = {
            PurePosixPath("src/main.py"): {"imports": ["src.utils"], "symbols": []},
            PurePosixPath("src/utils.py"): {"imports": [], "symbols": []},
        }

        html, stats = build_interactive_graph(modules)

        self.assertIn("src/main.py", html)
        self.assertIn("src/utils.py", html)
        self.assertEqual({"nodes": 2, "edges": 1}, stats)

    def test_repository_controlled_tooltip_text_is_escaped_and_json_safe(self):
        modules = {
            PurePosixPath("safe/<script>.py"): {
                "imports": ["utils"], "symbols": [{"kind": "function", "name": "<script>alert(1)</script>", "line": 1}],
                "extra": object(),
            }
        }
        html, stats = build_interactive_graph(modules)
        self.assertEqual({"nodes": 1, "edges": 0}, stats)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_graph_controls_and_exports_are_embedded(self):
        modules = {"src/api/routes.py": {"imports": [], "symbols": [], "lines": 5}}
        html, _ = build_interactive_graph(modules)
        for control in ("cb-search", "cb-package", "cb-layer", "cb-reset", "cb-export", "Direct dependencies", "Dependents"):
            self.assertIn(control, html)

    def test_analyzed_from_imports_resolve_to_real_local_modules(self):
        analysis = analyze_repository({
            "core/main.py": "from .utils import helper\n",
            "core/utils.py": "def helper():\n    return True\n",
            "other/utils.py": "def duplicate():\n    return False\n",
        })
        self.assertEqual({("core/main.py", "core/utils.py")},
                         resolve_local_dependencies(analysis["modules"]))

    def test_ambiguous_bare_imports_do_not_create_guessed_edges(self):
        modules = {
            "app.py": {"imports": ["utils"], "symbols": []},
            "one/utils.py": {"imports": [], "symbols": []},
            "two/utils.py": {"imports": [], "symbols": []},
        }
        self.assertEqual(set(), resolve_local_dependencies(modules))

    def test_pathlike_graph_metadata_can_be_serialized_to_json(self):
        safe = _json_safe({PurePosixPath("module"): {"path": PurePosixPath("src/main.py"),
                                                   "symbols": ({"name": "entry"},),
                                                   "unknown": object()}})
        encoded = json.dumps(safe)
        self.assertIn("src/main.py", encoded)


if __name__ == "__main__":
    unittest.main()
