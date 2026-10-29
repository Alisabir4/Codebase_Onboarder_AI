"""Generate documentation using only repository files and analyzer evidence."""
from pathlib import PurePosixPath
import json
import re
from core.rag import _SECRET


def generate_documentation(repo_files: dict[str, str], analysis: dict, label: str = "Repository") -> str:
    summary = analysis["summary"]
    lines = [f"# {label} — repository guide", "",
             "> Generated from files present in the analyzed repository. Interpretations are labeled as inferred.", "",
             "## Overview", "",
             f"Analyzed {summary['files_analyzed']} files, including {summary['python_files']} Python modules. "
             f"Detected {summary['functions']} functions and {summary['classes']} classes.", "",
             "## Languages", ""]
    for language, count in sorted(analysis["languages"].items(), key=lambda pair: (-pair[1], pair[0])):
        lines.append(f"- {language}: {count} file(s)")
    lines += ["", "## Technology evidence", ""]
    declared = set()
    if "requirements.txt" in repo_files:
        for line in repo_files["requirements.txt"].splitlines():
            match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
            if match and not line.lstrip().startswith(("#", "-", ".")):
                declared.add(match.group(1))
    if "package.json" in repo_files:
        try:
            manifest = json.loads(repo_files["package.json"])
            for section in ("dependencies", "devDependencies"):
                declared.update(str(name) for name in manifest.get(section, {}))
        except (TypeError, ValueError):
            pass
    lines.append("Declared dependencies: " + (", ".join(f"`{name}`" for name in sorted(declared))
                  if declared else "No dependency names could be safely derived from recognized manifests."))
    lines += ["", "## Directory and module map", ""]
    directories = sorted({str(PurePosixPath(path).parent) for path in analysis["file_details"]})
    for directory in directories:
        contents = [p for p in analysis["file_details"] if str(PurePosixPath(p).parent) == directory]
        lines.append(f"- `{directory or '.'}`: {', '.join(f'`{PurePosixPath(p).name}`' for p in contents)}")
        for path in contents:
            if path in analysis["modules"]:
                doc = analysis["modules"][path].get("docstring")
                if doc:
                    lines.append(f"  - `{path}`: {doc.splitlines()[0]} (repository docstring)")
                else:
                    lines.append(f"  - `{path}`: no module description was present; role is not inferred.")
    lines += ["", "## Setup", ""]
    setup_evidence = False
    for path in ("README.md", "requirements.txt", "pyproject.toml", "Pipfile", "package.json", "Makefile", "Dockerfile"):
        if path in repo_files:
            setup_evidence = True
            if path.lower() == "readme.md":
                lines.append("Setup guidance below is taken from the repository README:")
                lines.append("")
                lines.extend(f"> {_SECRET.sub(lambda m: f'{m.group(1)}{m.group(2)}[REDACTED]{m.group(4)}', line)}"
                             for line in repo_files[path].splitlines()[:40])
            else:
                lines.append(f"- Setup or dependency evidence: `{path}` is present.")
                if path == "requirements.txt":
                    lines.append("- Inferred install command from `requirements.txt`: `pip install -r requirements.txt`.")
                elif path == "pyproject.toml":
                    lines.append("- `pyproject.toml` is present; inspect its build configuration before choosing an install command.")
                elif path == "package.json":
                    lines.append("- Inferred install command from `package.json`: `npm install`.")
    if not setup_evidence:
        lines.append("No recognized setup manifest or README was found; installation commands are not inferred.")
    lines += ["", "## Important Python symbols", ""]
    for path, module in sorted(analysis["modules"].items()):
        lines.append(f"### `{path}`")
        if module["symbols"]:
            lines.extend(f"- {s['kind']}: `{s['name']}` (line {s['line']})" for s in module["symbols"])
        else:
            lines.append("- No functions or classes detected.")
        if module["imports"]:
            lines.append(f"- Imports: {', '.join(f'`{name}`' for name in module['imports'])}")
    lines += ["", "## API routes", ""]
    routes = []
    for path, content in repo_files.items():
        for number, text in enumerate(content.splitlines(), 1):
            if any(token in text for token in (
                "@app.route(", "@router.get(", "@router.post(", "@router.put(", "@router.patch(",
                "@router.delete(", "@app.get(", "@app.post(", "@app.put(", "@app.patch(", "@app.delete("
            )):
                routes.append(f"- `{path}:{number}` — `{text.strip()}` (route pattern detected; verify framework behavior)")
    lines.extend(routes or ["No common Flask/FastAPI route decorator patterns were detected."])
    lines += ["", "## Module relationships", ""]
    edges = []
    for path, module in analysis["modules"].items():
        for imported in module["imports"]:
            target = imported.lstrip(".")
            if target and any(target == p[:-3].replace("/", ".") or target.endswith("." + p[:-3].replace("/", ".")) for p in analysis["modules"] if p.endswith(".py")):
                edges.append(f"- `{path}` imports local module `{target}`")
    lines.extend(sorted(set(edges)) or ["No local import relationships were resolved."])
    lines += ["", "## Limitations", "", "This structural guide is generated from static text and AST inspection. Route and setup interpretations may be incomplete; it is not a security audit.", ""]
    return "\n".join(lines)
