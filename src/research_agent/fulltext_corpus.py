from __future__ import annotations

from pathlib import Path
import hashlib
import io
import os
import re
import stat

from .artifacts import write_json, write_text
from .models import FullTextCorpus, FullTextDocument


FULLTEXT_CORPUS_JSON = "01-fulltext-corpus.json"
FULLTEXT_CORPUS_MD = "01-fulltext-corpus.md"
MAX_CHARS_PER_CHUNK = 1400
CHUNK_OVERLAP = 160
FULLTEXT_MAX_BYTES_ENV = "RESEARCH_AGENT_FULLTEXT_MAX_BYTES"
FULLTEXT_ROOTS_ENV = "RESEARCH_AGENT_FULLTEXT_ROOTS"
FULLTEXT_MAX_FILES_ENV = "RESEARCH_AGENT_FULLTEXT_MAX_FILES"
FULLTEXT_MAX_TOTAL_BYTES_ENV = "RESEARCH_AGENT_FULLTEXT_MAX_TOTAL_BYTES"
FULLTEXT_MAX_PDF_PAGES_ENV = "RESEARCH_AGENT_FULLTEXT_MAX_PDF_PAGES"
FULLTEXT_MAX_PDF_CHARS_ENV = "RESEARCH_AGENT_FULLTEXT_MAX_PDF_CHARS"
DEFAULT_FULLTEXT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_FULLTEXT_MAX_FILES = 32
DEFAULT_FULLTEXT_MAX_TOTAL_BYTES = 64 * 1024 * 1024
DEFAULT_FULLTEXT_MAX_PDF_PAGES = 300
DEFAULT_FULLTEXT_MAX_PDF_CHARS = 2_000_000
SUPPORTED_FULLTEXT_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}


class FullTextLimitError(ValueError):
    pass


def build_fulltext_corpus(topic: str, paths: list[str], base_dir: Path | None = None) -> FullTextCorpus:
    base = (base_dir or Path.cwd()).expanduser().resolve()
    allowed_roots = _fulltext_allowed_roots(base)
    max_bytes = _fulltext_max_bytes()
    configured_paths = [str(value).strip() for value in paths if str(value).strip()]
    collection_issues = fulltext_collection_issues(configured_paths, base)
    if collection_issues:
        raise ValueError("; ".join(collection_issues))
    documents = [_load_document(value, base, allowed_roots, max_bytes) for value in configured_paths]
    warnings = [warning for document in documents for warning in document.warnings]
    total_chunks = sum(len(document.chunks) for document in documents)
    if paths and not documents:
        warnings.append("配置了全文路径，但没有成功读取任何文件。")
    return FullTextCorpus(topic=topic, documents=documents, total_chunks=total_chunks, warnings=warnings)


def write_fulltext_corpus_artifacts(topic: str, paths: list[str], out_dir: Path, base_dir: Path | None = None) -> FullTextCorpus:
    corpus = build_fulltext_corpus(topic, paths, base_dir=base_dir)
    write_json(out_dir / FULLTEXT_CORPUS_JSON, corpus)
    write_text(out_dir / FULLTEXT_CORPUS_MD, render_fulltext_corpus_markdown(corpus))
    return corpus


def render_fulltext_corpus_markdown(corpus: FullTextCorpus) -> str:
    lines = [
        f"# 全文语料：{corpus.topic}",
        "",
        f"- 文档数：{len(corpus.documents)}",
        f"- Chunk 数：{corpus.total_chunks}",
        "",
        "## 文档",
        "| 标题 | 状态 | Chunk | 字符数 | SHA256 | 路径 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    if not corpus.documents:
        lines.append("| 无 | - | 0 | 0 | - | - |")
    for document in corpus.documents:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(document.title),
                    document.status,
                    str(len(document.chunks)),
                    str(document.text_chars),
                    f"`{document.sha256}`",
                    _cell(document.path),
                ]
            )
            + " |"
        )
    if corpus.warnings:
        lines.extend(["", "## 警告"])
        lines.extend(f"- {item}" for item in corpus.warnings)
    lines.extend(["", "## Chunk 预览"])
    for document in corpus.documents:
        lines.append(f"### {document.title}")
        for index, chunk in enumerate(document.chunks[:3], start=1):
            preview = _short_text(chunk, 360)
            lines.extend([f"#### chunk {index}", preview, ""])
    return "\n".join(lines)


def inspect_fulltext_path(value: str, base_dir: Path | None = None) -> tuple[Path | None, str, str]:
    base = (base_dir or Path.cwd()).expanduser().resolve()
    return _inspect_fulltext_path(
        value,
        base,
        _fulltext_allowed_roots(base),
        _fulltext_max_bytes(),
    )


def fulltext_collection_issues(paths: list[str], base_dir: Path | None = None) -> list[str]:
    base = (base_dir or Path.cwd()).expanduser().resolve()
    values = [str(value).strip() for value in paths if str(value).strip()]
    issues: list[str] = []
    max_files = _positive_env_int(FULLTEXT_MAX_FILES_ENV, DEFAULT_FULLTEXT_MAX_FILES)
    if len(values) > max_files:
        issues.append(f"全文文件数量 {len(values)} 超过 {max_files} 上限")
        return issues
    allowed_roots = _fulltext_allowed_roots(base)
    max_file_bytes = _fulltext_max_bytes()
    total_bytes = 0
    for value in values:
        path, status, _warning = _inspect_fulltext_path(value, base, allowed_roots, max_file_bytes)
        if status != "ok" or path is None:
            continue
        try:
            total_bytes += path.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    max_total_bytes = _positive_env_int(FULLTEXT_MAX_TOTAL_BYTES_ENV, DEFAULT_FULLTEXT_MAX_TOTAL_BYTES)
    if total_bytes > max_total_bytes:
        issues.append(f"全文文件总大小 {total_bytes} 超过 {max_total_bytes} 字节上限")
    return issues


def _inspect_fulltext_path(
    value: str,
    base: Path,
    allowed_roots: list[Path],
    max_bytes: int,
) -> tuple[Path | None, str, str]:
    raw_path = Path(str(value).strip()).expanduser()
    path = raw_path if raw_path.is_absolute() else base / raw_path
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        return None, "blocked", f"全文路径无法解析：{value}: {exc}"
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return None, "blocked", f"全文路径超出允许根目录：{value}"
    if _path_contains_symlink(path):
        return None, "blocked", f"全文路径不能包含符号链接：{value}"
    if resolved.suffix.lower() not in SUPPORTED_FULLTEXT_SUFFIXES:
        return None, "blocked", f"不支持的全文文件类型 {resolved.suffix or '(none)'}：{value}"
    try:
        descriptor = _open_without_symlinks(resolved)
    except FileNotFoundError:
        return None, "missing", f"全文文件不存在：{value}"
    except OSError as exc:
        return None, "read_error", f"全文文件无法检查：{value}: {exc}"
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            return None, "blocked", f"全文路径不是普通文件：{value}"
        if file_stat.st_size > max_bytes:
            return None, "too_large", f"全文文件超过 {max_bytes} 字节上限：{value}"
    finally:
        os.close(descriptor)
    return resolved, "ok", ""


def _fulltext_max_bytes() -> int:
    return _positive_env_int(FULLTEXT_MAX_BYTES_ENV, DEFAULT_FULLTEXT_MAX_BYTES)


def _positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _fulltext_allowed_roots(base: Path) -> list[Path]:
    roots = [base / "fulltext", base / "benchmarks"]
    for value in os.environ.get(FULLTEXT_ROOTS_ENV, "").split(os.pathsep):
        if not value.strip():
            continue
        path = Path(value.strip()).expanduser()
        roots.append((path if path.is_absolute() else base / path).resolve())
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_contains_symlink(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return True
        except (FileNotFoundError, OSError):
            continue
    return False


def _open_without_symlinks(path: Path) -> int:
    absolute = path.absolute()
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    directory_descriptor = os.open(absolute.anchor, directory_flags)
    try:
        parts = absolute.parts[1:]
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=directory_descriptor)
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return os.open(parts[-1], file_flags, dir_fd=directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _read_regular_file(path: Path, max_bytes: int) -> bytes:
    descriptor = _open_without_symlinks(path)
    with os.fdopen(descriptor, "rb") as handle:
        file_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise OSError("path is not a regular file")
        if file_stat.st_size > max_bytes:
            raise ValueError(f"file exceeds {max_bytes} bytes")
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"file exceeds {max_bytes} bytes")
    return data


def _load_document(value: str, base_dir: Path, allowed_roots: list[Path], max_bytes: int) -> FullTextDocument:
    raw_path = Path(value.strip()).expanduser()
    path = raw_path if raw_path.is_absolute() else base_dir / raw_path
    title = _title_from_path(path)
    warnings: list[str] = []
    resolved, validation_status, validation_warning = _inspect_fulltext_path(
        value,
        base_dir,
        allowed_roots,
        max_bytes,
    )
    if resolved is None:
        return FullTextDocument(
            title=title,
            path=str(raw_path),
            sha256="",
            status=validation_status,
            text_chars=0,
            chunks=[],
            warnings=[validation_warning],
        )
    try:
        data = _read_regular_file(resolved, max_bytes)
    except OSError as exc:
        return FullTextDocument(
            title=title,
            path=str(raw_path),
            sha256="",
            status="read_error",
            text_chars=0,
            chunks=[],
            warnings=[f"全文文件读取失败：{value}: {exc}"],
        )
    except ValueError as exc:
        return FullTextDocument(
            title=title,
            path=str(raw_path),
            sha256="",
            status="too_large",
            text_chars=0,
            chunks=[],
            warnings=[f"全文文件读取被拒绝：{value}: {exc}"],
        )
    sha = hashlib.sha256(data).hexdigest()
    try:
        text, extract_warnings = _extract_text(resolved, data)
    except FullTextLimitError as exc:
        return FullTextDocument(
            title=title,
            path=str(raw_path),
            sha256=sha,
            status="too_large",
            text_chars=0,
            chunks=[],
            warnings=[f"全文 PDF 抽取被拒绝：{value}: {exc}"],
        )
    warnings.extend(extract_warnings)
    normalized = _normalize_text(text)
    chunks = _chunk_text(normalized)
    status = "ok" if chunks else "empty"
    if not chunks:
        warnings.append(f"全文文件未抽取到可用文本：{value}")
    return FullTextDocument(
        title=title,
        path=str(raw_path),
        sha256=sha,
        status=status,
        text_chars=len(normalized),
        chunks=chunks,
        warnings=warnings,
    )


def _extract_text(path: Path, data: bytes) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return data.decode("utf-8", errors="replace"), []
    if suffix == ".pdf":
        max_pages = _positive_env_int(FULLTEXT_MAX_PDF_PAGES_ENV, DEFAULT_FULLTEXT_MAX_PDF_PAGES)
        max_chars = _positive_env_int(FULLTEXT_MAX_PDF_CHARS_ENV, DEFAULT_FULLTEXT_MAX_PDF_CHARS)
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(data))
            page_count = len(reader.pages)
            if page_count > max_pages:
                raise FullTextLimitError(f"PDF 页数 {page_count} 超过 {max_pages} 上限")
            parts: list[str] = []
            extracted_chars = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                extracted_chars += len(page_text)
                if extracted_chars > max_chars:
                    raise FullTextLimitError(f"PDF 提取文本超过 {max_chars} 字符上限")
                parts.append(page_text)
            return "\n".join(parts), []
        except FullTextLimitError:
            raise
        except Exception as exc:
            fallback, truncated = _pdf_byte_fallback(data, max_chars)
            warning = f"PDF 正文抽取使用 fallback，建议安装 pypdf 或提供 txt/md：{path.name}: {exc}"
            warnings = [warning]
            if truncated:
                warnings.append(f"PDF fallback 文本已截断到 {max_chars} 字符。")
            return fallback, warnings
    raise ValueError(f"unsupported fulltext file type: {suffix or '(none)'}")


def _pdf_byte_fallback(data: bytes, max_chars: int) -> tuple[str, bool]:
    text = data.decode("latin-1", errors="ignore")
    snippets = re.findall(r"\(([^()]{20,})\)", text)
    if snippets:
        extracted = "\n".join(snippets)
        return extracted[:max_chars], len(extracted) > max_chars
    ascii_text = re.sub(r"[^A-Za-z0-9.,;:!?()\-\s]", " ", text)
    extracted = re.sub(r"\s+", " ", ascii_text)
    return extracted[:max_chars], len(extracted) > max_chars


def _chunk_text(text: str) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + MAX_CHARS_PER_CHUNK)
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end), text.rfind("。", start, end))
            if boundary > start + 300:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title_from_path(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    return stem or path.name or "local fulltext"


def _short_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
