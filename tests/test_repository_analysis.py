import io
import zipfile
import unittest
from unittest.mock import Mock, patch

from core.analyzer import analyze_repository
from core.github_loader import load_zip_repository, load_github_repository
from core.graph_builder import build_interactive_graph


def repository_zip(root="ops-copilot-main"):
    files = {
        f"{root}/app.py": "from package.worker import run\n\ndef main():\n    return run()\n",
        f"{root}/package/worker.py": "from .models import Job\n\nclass Worker:\n    pass\n\ndef run():\n    return Job()\n",
        f"{root}/package/models.py": "class Job:\n    pass\n\ndef create_job():\n    return Job()\n",
        f"{root}/package/nested/helper.py": "def help_task():\n    return True\n",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


class RepositoryAnalysisTests(unittest.TestCase):
    def test_github_style_zip_preserves_nested_modules_and_analyzes_ast(self):
        upload = Mock()
        upload.getvalue.return_value = repository_zip()
        upload.name = "ops-copilot.zip"

        files, _ = load_zip_repository(upload)
        result = analyze_repository(files)
        _, graph = build_interactive_graph(result["modules"])

        self.assertEqual(4, result["summary"]["files_analyzed"])
        self.assertEqual(4, result["summary"]["python_files"])
        self.assertEqual(4, result["summary"]["functions"])
        self.assertEqual(2, result["summary"]["classes"])
        self.assertIn("package/nested/helper.py", files)
        self.assertEqual(4, graph["nodes"])
        self.assertGreaterEqual(graph["edges"], 2)

    @patch("core.github_loader._repository_cache", {})
    @patch("core.github_loader.requests.Session")
    def test_github_loader_reads_all_files_from_downloaded_archive(self, session_factory):
        metadata = Mock(status_code=200, headers={})
        metadata.json.return_value = {"default_branch": "main"}
        archive_response = Mock(status_code=200, headers={})
        archive_response.__enter__ = Mock(return_value=archive_response)
        archive_response.__exit__ = Mock(return_value=False)
        archive_response.iter_content.return_value = [repository_zip()]
        session_factory.return_value.get.side_effect = [metadata, archive_response]

        files, label = load_github_repository("https://github.com/owner/repo")

        self.assertEqual("owner/repo", label)
        self.assertEqual(4, len(files))
        self.assertIn("package/nested/helper.py", files)
        self.assertEqual(2, session_factory.return_value.get.call_count)
        self.assertTrue(session_factory.return_value.get.call_args.kwargs.get("stream"))

    def test_zip_filters_secrets_dependencies_and_traversal(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("project/src/main.py", "def main(): pass")
            archive.writestr("project/.env", "TOKEN=secret")
            archive.writestr("project/node_modules/pkg/index.py", "def ignored(): pass")
            archive.writestr("project/../../outside.py", "def unsafe(): pass")
        upload = Mock()
        upload.getvalue.return_value = output.getvalue()
        files, _ = load_zip_repository(upload)
        self.assertEqual({"src/main.py"}, set(files))

    def test_malformed_zip_has_clear_error(self):
        upload = Mock()
        upload.getvalue.return_value = b"not a zip"
        with self.assertRaisesRegex(ValueError, "not a valid ZIP"):
            load_zip_repository(upload)


if __name__ == "__main__":
    unittest.main()
