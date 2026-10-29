import sys
import types
import unittest
from unittest.mock import patch

from core.analyzer import analyze_repository
from core.documentation import generate_documentation
from core.rag import chunk_repository, retrieve


class FeatureTests(unittest.TestCase):
    def test_analysis_filters_secrets_and_flags_structural_heuristics(self):
        result = analyze_repository({
            "app.py": "API_KEY = 'super-secret-value-123'\ndef public():\n    pass\n",
            ".env": "API_KEY=should-not-be-analyzed",
            "venv/pkg.py": "def hidden(): pass",
        })
        self.assertEqual(["app.py"], list(result["file_details"]))
        self.assertTrue(any("may contain a hardcoded credential" in issue and "123" not in issue
                            for issue in result["findings"]))
        self.assertTrue(any("no module docstring" in issue for issue in result["findings"]))

    def test_rag_chunking_preserves_paths_lines_and_excludes_filtered_files(self):
        source = "\n".join(f"line {i}" for i in range(1, 100))
        chunks = chunk_repository({"src/main.py": source, ".env": "secret", "node_modules/lib.py": "ignored"})
        self.assertEqual(2, len(chunks))
        self.assertEqual((1, 80), (chunks[0]["start_line"], chunks[0]["end_line"]))
        self.assertEqual((69, 99), (chunks[1]["start_line"], chunks[1]["end_line"]))
        self.assertEqual("src/main.py", chunks[0]["path"])

    def test_rag_and_generated_docs_redact_hardcoded_secret_values(self):
        files = {"README.md": "# setup\nAPI_KEY=sk_live_abcdefghijk123\n",
                 "config.py": "API_KEY = 'sk_live_abcdefghijk123'\n"}
        chunks = chunk_repository(files)
        docs = generate_documentation(files, analyze_repository(files))
        combined = "\n".join(chunk["text"] for chunk in chunks) + docs
        self.assertNotIn("sk_live_abcdefghijk123", combined)
        self.assertIn("[REDACTED]", combined)

    def test_retrieval_returns_cited_source_chunks(self):
        class Vectors(list):
            @property
            def shape(self):
                return (len(self), len(self[0]))
            def __matmul__(self, query):
                return [sum(a * b for a, b in zip(row, query)) for row in self]

        class FakeModel:
            def encode(self, texts, **kwargs):
                return Vectors([[1.0, 0.0] if "router" in text else [0.0, 1.0]
                                for text in texts])

        class FakeIndex:
            def __init__(self, dimensions):
                self.vectors = None
            def add(self, vectors):
                self.vectors = vectors
            def search(self, query, count):
                scores = self.vectors @ query[0]
                ids = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:count]
                return [ [scores[i] for i in ids] ], [ids]

        fake_faiss = types.SimpleNamespace(IndexFlatIP=FakeIndex)
        fake_transformers = types.SimpleNamespace(SentenceTransformer=lambda name: FakeModel())
        with patch.dict(sys.modules, {"faiss": fake_faiss,
                                     "sentence_transformers": fake_transformers}):
            results = retrieve({"api/router.py": "router endpoint".ljust(100),
                                "utils.py": "general utility".ljust(100)}, "router")
        self.assertEqual("api/router.py", results[0]["path"])
        self.assertEqual(1, results[0]["start_line"])
        self.assertGreater(results[0]["score"], 0.9)

    def test_documentation_is_grounded_in_repository_files(self):
        files = {"app.py": "from core.api import start\n\ndef main():\n    start()\n",
                 "requirements.txt": "streamlit\n", "README.md": "# Project\n\nRun with streamlit run app.py"}
        analysis = analyze_repository(files)
        docs = generate_documentation(files, analysis, "Sample")
        self.assertIn("# Sample — repository guide", docs)
        self.assertIn("`requirements.txt`", docs)
        self.assertIn("`main`", docs)


if __name__ == "__main__":
    unittest.main()
