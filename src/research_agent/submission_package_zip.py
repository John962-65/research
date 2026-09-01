from __future__ import annotations

from pathlib import Path
import json
import zipfile


SUBMISSION_PACKAGE_ZIP_REQUIRED_ENTRIES = {
    "submission-package/CHECKLIST.md",
    "submission-package/package-manifest.json",
}
SUBMISSION_PACKAGE_FILE_STATUSES = {
    "pass",
    "generated",
    "missing",
    "optional_missing",
    "error",
    "skipped",
}


def submission_package_zip_ready(path: Path) -> bool:
    return not submission_package_zip_blocking_issue(path)


def submission_package_zip_blocking_issue(path: Path, *, package_zip_name: str | None = None, require_safe_filename: bool = False) -> str:
    zip_name = package_zip_name or path.name
    if require_safe_filename and not safe_submission_package_zip_filename(zip_name):
        return f"{zip_name or '11-submission-package.zip'} 路径不安全，必须是 run 目录下的 ZIP 文件名。"
    if not _nonempty_file(path):
        return f"{zip_name} 缺失或为空。"
    try:
        with zipfile.ZipFile(path) as archive:
            name_list = archive.namelist()
            names = set(name_list)
            if archive.testzip() is not None:
                return f"{zip_name} ZIP 完整性校验失败。"
            if len(names) != len(name_list):
                return f"{zip_name} 包含重复的包内路径。"
            if not _zip_entries_safe(names):
                return f"{zip_name} 包含不安全的包内路径。"
            missing = sorted(SUBMISSION_PACKAGE_ZIP_REQUIRED_ENTRIES - names)
            if missing:
                return f"{zip_name} 缺少投稿包清单：{', '.join(missing)}。"
            manifest_issue = _package_manifest_issue(archive, names)
            if manifest_issue:
                return f"{zip_name} {manifest_issue}"
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, json.JSONDecodeError):
        return f"{zip_name} 不是可读 ZIP。"
    return ""


def safe_submission_package_zip_filename(name: str) -> bool:
    if not name or "/" in name or "\\" in name:
        return False
    if name in {".", ".."} or _windows_drive_absolute(name):
        return False
    return Path(name).name == name and name.endswith(".zip")


def _package_manifest_issue(archive: zipfile.ZipFile, names: set[str]) -> str:
    data = json.loads(archive.read("submission-package/package-manifest.json").decode("utf-8"))
    if not isinstance(data, dict):
        return "package-manifest.json 不是 JSON object。"
    files = data.get("files")
    if not bool(str(data.get("status") or "").strip()):
        return "package-manifest.json 缺少 status。"
    if not isinstance(files, list) or not files:
        return "package-manifest.json 缺少 files 清单。"
    seen_package_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            return "package-manifest.json files 包含非 object 项。"
        package_path = str(item.get("package_path") or "").strip()
        status = str(item.get("status") or "").strip()
        if not package_path:
            return "package-manifest.json files 包含空 package_path。"
        if not _zip_entry_safe(package_path):
            return f"package-manifest.json files 包含不安全路径：{package_path}。"
        if package_path in seen_package_paths:
            return f"package-manifest.json files 包含重复路径：{package_path}。"
        seen_package_paths.add(package_path)
        if "status" in item and status not in SUBMISSION_PACKAGE_FILE_STATUSES:
            return f"package-manifest.json files 包含未知 status：{status or 'empty'}。"
        if "required" in item and not isinstance(item.get("required"), bool):
            return f"package-manifest.json files 中 {package_path} 的 required 不是 boolean。"
        if "bytes" in item and not _nonnegative_int(item.get("bytes")):
            return f"package-manifest.json files 中 {package_path} 的 bytes 不是非负整数。"
        if "sha256" in item and not _manifest_sha256_ok(item.get("sha256")):
            return f"package-manifest.json files 中 {package_path} 的 sha256 格式不合法。"
        if package_path.startswith("submission-package/") and status not in {"missing", "optional_missing", "error", "skipped"} and package_path not in names:
            return f"package-manifest.json 列出的 {package_path} 不在 ZIP 中。"
    return ""


def _zip_entries_safe(names: set[str]) -> bool:
    return bool(names) and all(_zip_entry_safe(name) for name in names)


def _zip_entry_safe(name: str) -> bool:
    if not name or "\\" in name:
        return False
    if name.startswith("/") or _windows_drive_absolute(name):
        return False
    parts = name.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _windows_drive_absolute(path: str) -> bool:
    return len(path) >= 2 and path[0].isalpha() and path[1] == ":"


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _manifest_sha256_ok(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value == "" or (len(value) == 64 and all(char in "0123456789abcdef" for char in value))


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False
