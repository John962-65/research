from __future__ import annotations

from pathlib import Path


_PYTHON_INTERPRETERS = {"python", "python2", "python3", "pypy", "pypy2", "pypy3"}
_SHELL_INTERPRETERS = {"sh", "bash", "dash", "zsh", "fish", "ksh"}
_EVAL_INTERPRETERS = {"node", "nodejs", "ruby", "perl", "php", "lua", "r"}
_DYNAMIC_FLAGS = {
    "-c",
    "--command",
    "-e",
    "--eval",
    "--evaluate",
    "-p",
    "--print",
}


def interpreter_execution_issues(command: list[str]) -> list[str]:
    """Reject interpreter modes that execute inline code or installed modules.

    The executable allowlist controls which binary may start. This second layer
    ensures an approved interpreter can only run a reviewed relative script.
    """
    if not command:
        return []
    executable = Path(str(command[0]).strip()).name.lower()
    tokens = [str(value).strip() for value in command[1:]]
    issues: list[str] = []

    if executable in {"eval", "exec"}:
        return [f"命令 '{executable}' 是动态代码执行入口，禁止运行"]

    if executable in _PYTHON_INTERPRETERS:
        issues.extend(_forbidden_flag_issues(tokens, {*_DYNAMIC_FLAGS, "-m", "--module"}))
        if not issues and not _first_script(tokens, {".py"}):
            issues.append("Python 解释器必须执行 experiments/ 内明确的 .py 脚本，禁止交互、stdin、-c 或 -m 执行")
    elif executable in _SHELL_INTERPRETERS:
        issues.extend(_forbidden_flag_issues(tokens, _DYNAMIC_FLAGS))
        if not issues and not _first_script(tokens, {".sh"}):
            issues.append("Shell 解释器必须执行 experiments/ 内明确的 .sh 脚本，禁止 -c/--command 或 stdin 执行")
    elif executable in _EVAL_INTERPRETERS:
        issues.extend(_forbidden_flag_issues(tokens, {*_DYNAMIC_FLAGS, "-r", "--require"}))
        if not issues and not _first_script(tokens, _script_suffixes(executable)):
            issues.append(f"解释器 '{executable}' 必须执行明确的相对脚本，禁止 eval/require/stdin 执行")
    return issues


def _forbidden_flag_issues(tokens: list[str], forbidden: set[str]) -> list[str]:
    issues: list[str] = []
    for index, token in enumerate(tokens, start=1):
        normalized = token.lower()
        if normalized in forbidden or any(normalized.startswith(flag + "=") for flag in forbidden if flag.startswith("--")):
            issues.append(f"命令参数 #{index} 使用动态代码/模块执行选项：{token}")
            continue
        if any(normalized.startswith(flag) and normalized != flag for flag in {"-c", "-e"} if flag in forbidden):
            issues.append(f"命令参数 #{index} 使用内联代码执行选项：{token}")
    return issues


def _first_script(tokens: list[str], suffixes: set[str]) -> str:
    for token in tokens:
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        return token if Path(token).suffix.lower() in suffixes else ""
    return ""


def _script_suffixes(executable: str) -> set[str]:
    return {
        "node": {".js", ".cjs", ".mjs"},
        "nodejs": {".js", ".cjs", ".mjs"},
        "ruby": {".rb"},
        "perl": {".pl", ".pm"},
        "php": {".php"},
        "lua": {".lua"},
        "r": {".r"},
    }.get(executable, set())
