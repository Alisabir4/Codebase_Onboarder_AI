import ast
import re
from collections import Counter
from pathlib import PurePosixPath

IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".idea",
    ".vscode", "dist", "build", "coverage", ".next", "site-packages"
}
IGNORED_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".gz", ".sqlite", ".db", ".mp4", ".mov", ".mp3", ".wav", ".pyc",
    ".onnx", ".pt", ".pth", ".bin", ".lock"
}
TEXT_SUFFIX_LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript/JSX",
    ".ts": "TypeScript", ".tsx": "TypeScript/TSX", ".java": "Java",
    ".cs": "C#", ".cpp": "C++", ".c": "C", ".go": "Go", ".rs": "Rust",
    ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".kt": "Kotlin",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".md": "Markdown",
    ".sql": "SQL", ".sh": "Shell", ".bat": "Batch", ".ps1": "PowerShell",
    ".xml": "XML", ".vue": "Vue", ".svelte": "Svelte"
}
MAX_FILE_BYTES = 1_000_000
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|secret|password|token|access[_-]?key)\b\s*[:=]\s*)(['\"]?)([^\s,'\"#]{8,})(['\"]?)"
)
_PLACEHOLDER_SECRET = re.compile(r"(?i)(changeme|example|placeholder|dummy|your[_ -]|test[_ -]?key|xxx|^\*+$)")


def _is_ignored(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part in IGNORED_DIRS for part in p.parts):
        return True
    if p.suffix.lower() in IGNORED_SUFFIXES:
        return True
    if p.name.lower() in {".env", ".env.local", ".env.production"}:
        return True
    if p.name.lower().endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return False


def analyze_repository(repo_files: dict[str, str], max_files: int = 800) -> dict:
    languages = Counter()
    file_details = {}
    modules = {}
    findings = []
    parse_errors = 0
    functions = 0
    classes = 0
    imports_detected = 0
    files_skipped = 0

    candidates = sorted(repo_files.items())
    if len(candidates) > max_files:
        files_skipped += len(candidates) - max_files
        candidates = candidates[:max_files]

    for path, content in candidates:
        if _is_ignored(path):
            files_skipped += 1
            continue
        suffix = PurePosixPath(path).suffix.lower()
        language = TEXT_SUFFIX_LANGUAGES.get(suffix, "Other")
        languages[language] += 1
        line_count = content.count("\n") + (1 if content else 0)
        detail = {
            "language": language,
            "lines": line_count,
            "symbols": [],
            "imports": [],
        }

        if suffix == ".py":
            try:
                tree = ast.parse(content, filename=path)
                if ast.get_docstring(tree) is None and tree.body:
                    findings.append(f"[Heuristic] `{path}:1` has no module docstring.")
                import_names = []
                local_import_names = []
                symbols = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions += 1
                        symbols.append({"kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                                        "name": node.name, "line": getattr(node, "lineno", 1)})
                        if node.end_lineno - node.lineno + 1 > 80:
                            findings.append(f"[Heuristic] `{path}:{node.lineno}` function `{node.name}` spans more than 80 lines.")
                        if not node.name.startswith("_") and ast.get_docstring(node) is None:
                            findings.append(f"[Heuristic] `{path}:{node.lineno}` public function `{node.name}` has no docstring.")
                    elif isinstance(node, ast.ClassDef):
                        classes += 1
                        symbols.append({"kind": "class", "name": node.name, "line": getattr(node, "lineno", 1)})
                        if not node.name.startswith("_") and ast.get_docstring(node) is None:
                            findings.append(f"[Heuristic] `{path}:{node.lineno}` public class `{node.name}` has no docstring.")
                    elif isinstance(node, ast.Import):
                        import_names.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imported_module = "." * (node.level or 0) + (node.module or "")
                        import_names.append(imported_module)
                        local_import_names.extend(imported_module + ("." if imported_module and not imported_module.endswith(".") else "") + alias.name
                                                  for alias in node.names if alias.name != "*")
                detail["symbols"] = sorted(symbols, key=lambda s: s["line"])
                detail["imports"] = sorted(set(n for n in import_names if n))
                imports_detected += len(import_names)
                modules[path] = {
                    "imports": detail["imports"],
                    "local_imports": sorted(set(n for n in local_import_names if n)),
                    "symbols": detail["symbols"],
                    "lines": line_count,
                    "docstring": ast.get_docstring(tree),
                }
                if not tree.body or all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                                        and isinstance(node.value.value, str) for node in tree.body):
                    findings.append(f"[Heuristic] `{path}:1` is an empty module (no executable declarations).")
            except (SyntaxError, ValueError, TypeError) as exc:
                parse_errors += 1
                findings.append(f"Could not parse `{path}`: {type(exc).__name__}.")
        file_details[path] = detail

        for number, line in enumerate(content.splitlines(), 1):
            match = _SECRET_ASSIGNMENT.search(line)
            if match and not _PLACEHOLDER_SECRET.search(match.group(3)):
                findings.append(f"[Heuristic] `{path}:{number}` may contain a hardcoded credential; value omitted.")
            if re.search(r"\b(TODO|FIXME)\b", line, re.IGNORECASE):
                marker = re.search(r"\b(TODO|FIXME)\b", line, re.IGNORECASE).group(1).upper()
                findings.append(f"[Heuristic] `{path}:{number}` contains a {marker} marker.")

        if suffix == ".py" and path in modules:
            try:
                tree = ast.parse(content, filename=path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler) and (
                        node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception")
                    ):
                        findings.append(f"[Heuristic] `{path}:{node.lineno}` catches a broad exception type.")
            except (SyntaxError, ValueError, TypeError):
                pass

    for path, content in candidates:
        if _is_ignored(path):
            continue
        if len(content.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
            findings.append(f"`{path}` exceeds the 1 MB per-file analysis limit.")
        if PurePosixPath(path).name in {"requirements.txt", "pyproject.toml", "package.json"}:
            if not content.strip():
                findings.append(f"`{path}` is empty; verify whether dependencies are documented.")

    if not modules:
        findings.append("No Python source modules were detected; the first version builds deep dependency maps for Python repositories.")
    if parse_errors:
        findings.append(f"{parse_errors} Python file(s) could not be parsed. Check syntax or generated files.")

    summary = {
        "files_discovered": len(repo_files),
        "files_analyzed": len(file_details),
        "files_skipped": files_skipped,
        "python_files": sum(1 for p in file_details if PurePosixPath(p).suffix.lower() == ".py"),
        "functions": functions,
        "classes": classes,
        "imports_detected": imports_detected,
        "parse_errors": parse_errors,
    }
    return {
        "summary": summary,
        "languages": dict(languages),
        "file_details": file_details,
        "modules": modules,
        "findings": findings,
    }
