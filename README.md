# Codebase Onboarder AI

A Streamlit tool for exploring public GitHub repositories and repository ZIP files. It inspects source as text, extracts Python structure with `ast`, maps local imports, and can optionally search and answer questions using local models.

## Features

- Public GitHub ZIP download and ZIP upload with file-count, download, extraction, per-file-size, path traversal, binary, secret-file, and dependency-folder filters.
- Language and file summaries plus Python function, class, and import extraction.
- Interactive PyVis module graph with local import links and module details.
- Read-only file and symbol explorer with search, line numbers, and syntax highlighting.
- Grounded Markdown documentation generated from repository files and static analysis.
- Optional semantic retrieval using Sentence Transformers and FAISS, with optional local Ollama answers and source path/line citations.
- Explainable structural findings for missing docstrings, long functions, empty modules, and likely hardcoded credentials. These checks are heuristics, not a security audit.
- No paid service or API key is required to run the base application.

## Requirements and setup

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

On macOS/Linux, activate with `source .venv/bin/activate` and use the same `pip install` and `streamlit run` commands.

Run the offline test suite with `pip install -r requirements-dev.txt` followed by `python -m pytest -q`. Tests mock GitHub HTTP responses and use a fake embedding/index backend; they do not need live services.

The base app does not download embedding models. To enable semantic search, install the optional dependencies:

```powershell
pip install -r requirements-rag.txt
```

Sentence Transformers may download its configured model the first time semantic search runs. FAISS CPU wheels depend on platform support; if unavailable, the base app still runs, but semantic chat requires a compatible environment.

For generated answers, install and start [Ollama](https://ollama.com), then pull a model, for example `ollama pull llama3.2`. Enter the installed model name in the Codebase Chat tab. Ollama is contacted at `http://localhost:11434`; this is configurable through `OLLAMA_BASE_URL`. If Ollama is unavailable, the app reports setup guidance and does not invent an answer. Without the optional embedding packages, retrieval does not fall back to fabricated results.

## Architecture

- `app.py`: Streamlit UI and session state.
- `core/github_loader.py`: GitHub metadata/ZIP download, ZIP ingestion, limits, and filtering.
- `core/analyzer.py`: file/language analysis, Python AST symbols/imports, and structural findings.
- `core/graph_builder.py`: local module matching and interactive graph HTML.
- `core/rag.py`: source chunking, optional semantic index/retrieval, and optional Ollama calls.
- `core/documentation.py`: repository-grounded Markdown generation.
- `tests/`: offline tests; GitHub requests are mocked.

Repository code is never imported or executed. The architecture graph only draws links it can resolve to modules present in the analyzed repository. Import resolution is static and may miss dynamic imports, aliases, or unusual project layouts.

## Configuration and limits

GitHub loading is limited to public repositories. Current defaults limit the compressed archive to 30 MB, uncompressed ZIP content to 100 MB, each file to 1 MB, and analyzed files to 800 (adjustable in the sidebar). Repositories containing excluded dependency/build folders, binary data, secret files, or oversized files will have those entries skipped. RAG indexes are kept in process memory and keyed by repository content and embedding model; changing repositories naturally selects a different index. No API-based provider is configured or enabled.

## Screenshots

_Screenshot placeholder: Overview and repository metrics._

_Screenshot placeholder: Interactive architecture graph._

_Screenshot placeholder: Codebase Chat with source citations._

## Streamlit Community Cloud deployment

1. Push this project to a GitHub repository.
2. In Streamlit Community Cloud, create an app from that repository and set the entry point to `app.py`.
3. Install the base dependencies from `requirements.txt` during deployment. The base app does not require `requirements-rag.txt` and remains usable without embeddings, Ollama, credentials, or paid services.
4. Enable semantic retrieval only if the deployment platform supports the optional Sentence Transformers and FAISS dependencies and has enough disk/memory for the model. Ollama generally belongs on a reachable local/private host; a cloud app cannot reach a developer's `localhost`.

## Limitations

- Deep symbol parsing is Python-focused. Other recognized text file types are counted and browsable but not parsed into symbols.
- Semantic retrieval requires optional packages and model availability. Ollama is optional and must be running separately.
- API route recognition uses common source patterns and is labeled as an observation, not a complete endpoint inventory.
- Secret detection and code-quality findings are heuristics and can produce false positives or miss cases. This is not a security audit.
- The graph and documentation are based on static imports and files retained by ingestion filters; dynamic behavior is not executed.
