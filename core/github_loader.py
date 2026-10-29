import io
import re
import threading
import time
import zipfile
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import PurePosixPath
from urllib.parse import urlparse
import requests

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 1_000_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".sqlite", ".db", ".mp4", ".mov", ".mp3", ".wav", ".pyc", ".pt", ".pth",
    ".onnx", ".bin", ".lock"
}
SKIP_NAMES = {".env", ".env.local", ".env.production"}
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
_REPOSITORY_CACHE_TTL = 300
_REPOSITORY_CACHE_MAX_ENTRIES = 32
_repository_cache = {}
_repository_cache_lock = threading.Lock()


def _github_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "User-Agent": "Codebase-Onboarder-AI/1.0 (+https://github.com)",
    })
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def _raise_github_error(response) -> None:
    status = response.status_code
    if status == 404:
        raise ValueError("Repository not found or not public. Private repositories are not supported.")
    if status == 429 or (status == 403 and response.headers.get("X-RateLimit-Remaining") == "0"):
        reset = response.headers.get("X-RateLimit-Reset")
        detail = f" Try again after the rate limit resets (Unix time {reset})." if reset else " Please try again later."
        raise ValueError("GitHub API rate limit reached." + detail)
    if status == 403:
        raise ValueError("GitHub denied this request. Check the repository URL and try again later.")
    if status >= 500:
        raise ValueError("GitHub is temporarily unavailable. Please try again shortly.")
    response.raise_for_status()


def _should_skip(path: str) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        return True
    if any(part in SKIP_DIRS for part in p.parts):
        return True
    if p.name.lower() in SKIP_NAMES or p.name.lower().endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return p.suffix.lower() in SKIP_SUFFIXES


def _decode_text(data: bytes) -> str | None:
    if len(data) > MAX_SINGLE_FILE_BYTES or b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    # Avoid treating huge/minified binary-like data as source.
    return text


def _read_zip_bytes(zip_bytes: bytes, max_files: int) -> dict[str, str]:
    if len(zip_bytes) > MAX_DOWNLOAD_BYTES:
        raise ValueError("ZIP download exceeds the 30 MB compressed-size limit.")
    output = {}
    total_uncompressed = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from exc

    with archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        # GitHub ZIPs share one generated repository root. Strip it only when
        # every member has that same root; ordinary project folders are real paths.
        roots = {PurePosixPath(m.filename.replace("\\", "/")).parts[0]
                 for m in members if PurePosixPath(m.filename.replace("\\", "/")).parts}
        strip_root = next(iter(roots)) if len(roots) == 1 else None
        for member in members:
            normalized = member.filename.replace("\\", "/")
            p = PurePosixPath(normalized)
            if p.is_absolute() or ".." in p.parts or _should_skip(normalized):
                continue
            if member.file_size > MAX_SINGLE_FILE_BYTES:
                continue
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_UNZIPPED_BYTES:
                raise ValueError("ZIP exceeds the 100 MB uncompressed-size limit.")
            if len(output) >= max_files:
                break
            try:
                data = archive.read(member)
            except (RuntimeError, zipfile.BadZipFile):
                continue
            text = _decode_text(data)
            if text is None:
                continue
            # GitHub ZIPs wrap everything in one root directory. Strip that prefix.
            parts = p.parts
            rel_parts = parts[1:] if strip_root and parts[0] == strip_root else parts
            rel = "/".join(rel_parts)
            if not rel or _should_skip(rel):
                continue
            output[rel] = text
    if not output:
        raise ValueError("No readable source/configuration files were found in the ZIP.")
    return output


def load_zip_repository(uploaded_file, max_files: int = 800):
    raw = uploaded_file.getvalue()
    files = _read_zip_bytes(raw, max_files)
    label = getattr(uploaded_file, "name", "uploaded-repository.zip")
    return files, label


def load_github_repository(url: str, max_files: int = 800):
    try:
        parsed = urlparse(url.strip())
        valid_host = (parsed.scheme == "https" and parsed.hostname in {"github.com", "www.github.com"}
                      and not parsed.username and not parsed.password and parsed.port in (None, 443)
                      and not parsed.query and not parsed.fragment)
    except (AttributeError, ValueError):
        valid_host = False
    if not valid_host:
        raise ValueError("Please provide an HTTPS URL from github.com.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("Use a repository URL like https://github.com/owner/repository.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise ValueError("The repository URL contains invalid owner/repository characters.")

    cache_key = (owner.lower(), repo.lower(), max_files)
    now = time.monotonic()
    with _repository_cache_lock:
        cached = _repository_cache.get(cache_key)
        if cached and now - cached[0] < _REPOSITORY_CACHE_TTL:
            return dict(cached[1]), f"{owner}/{repo}"
        _repository_cache.pop(cache_key, None)

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    session = _github_session()
    try:
        response = session.get(api_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        _raise_github_error(response)
        default_branch = response.json().get("default_branch")
        if not default_branch:
            raise ValueError("GitHub did not return a default branch for this repository.")

        archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{default_branch}"
        with session.get(archive_url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=True) as archive_response:
            _raise_github_error(archive_response)
            chunks = []
            total = 0
            for chunk in archive_response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Repository ZIP exceeds the 30 MB download limit.")
                chunks.append(chunk)
    except ValueError:
        raise
    except requests.Timeout as exc:
        raise ValueError("The connection to GitHub timed out. Please try again.") from exc
    except requests.ConnectionError as exc:
        raise ValueError("Could not connect to GitHub. Check your internet connection and try again.") from exc
    except requests.RequestException as exc:
        raise ValueError("GitHub could not complete the repository download. Please try again.") from exc
    files = _read_zip_bytes(b"".join(chunks), max_files)
    with _repository_cache_lock:
        if len(_repository_cache) >= _REPOSITORY_CACHE_MAX_ENTRIES:
            oldest = min(_repository_cache, key=lambda key: _repository_cache[key][0])
            _repository_cache.pop(oldest, None)
        _repository_cache[cache_key] = (time.monotonic(), dict(files))
    return files, f"{owner}/{repo}"
