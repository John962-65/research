"""项目存储层：原子 JSON 写、JSONL 追加、事件日志、路径安全。

数据布局（数据根目录默认 ./data，可用 RESEARCH_COPILOT_DATA_DIR 覆盖）：
    <data_root>/projects/<project_id>/project.json
    <data_root>/projects/<project_id>/materials.json
    <data_root>/projects/<project_id>/research-state.json
    <data_root>/projects/<project_id>/hypotheses.json
    <data_root>/projects/<project_id>/experiments.json
    <data_root>/projects/<project_id>/decisions.jsonl
    <data_root>/projects/<project_id>/evidence-ledger.jsonl
    <data_root>/projects/<project_id>/events.jsonl
    <data_root>/projects/<project_id>/observations.json
    <data_root>/projects/<project_id>/findings.json
    <data_root>/projects/<project_id>/diagnosis/diag-NNN.json|.md
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import (
    DecisionRecord,
    EvidenceEntry,
    ExperimentCandidate,
    Finding,
    Hypothesis,
    Material,
    Observation,
    OpenQuestion,
    Project,
    ResearchState,
)

_SLUG_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(text: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("-", text.strip()).strip("-")
    return slug[:max_len] or "project"


class ProjectStore:
    def __init__(self, data_root: str | os.PathLike[str] | None = None) -> None:
        root = data_root or os.environ.get("RESEARCH_COPILOT_DATA_DIR") or "data"
        self.data_root = Path(root).resolve()

    # ---------- 路径安全 ----------
    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[0-9A-Za-z\u4e00-\u9fff._-]+", project_id or ""):
            raise ValueError(f"非法项目 ID: {project_id!r}")
        path = (self.data_root / "projects" / project_id).resolve()
        if self.data_root not in path.parents and path != self.data_root:
            raise ValueError("项目目录越出数据根目录")
        return path

    # ---------- 原子写 ----------
    @staticmethod
    def _atomic_write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    # ---------- 事件日志 ----------
    def log_event(self, project_id: str, action: str, target: str = "", detail: str = "", actor: str = "system") -> None:
        self.append_jsonl(
            self.project_dir(project_id) / "events.jsonl",
            {"ts": now_iso(), "actor": actor, "action": action, "target": target, "detail": detail},
        )

    # ---------- 项目生命周期 ----------
    def create_project(self, name: str, description: str = "", goals: Iterable[str] = ()) -> Project:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        project_id = f"{stamp}-{slugify(name)}" if slugify(name) != "project" else stamp
        project = Project(
            id=project_id,
            name=name,
            description=description,
            goals=[g for g in goals if g],
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        pdir = self.project_dir(project_id)
        if pdir.exists():
            raise RuntimeError(f"项目目录已存在: {pdir}")
        pdir.mkdir(parents=True)
        self._atomic_write_json(pdir / "project.json", project.to_dict())
        self._atomic_write_json(pdir / "research-state.json", ResearchState(updated_at=now_iso()).to_dict())
        self.log_event(project_id, "project_created", target=project_id, detail=name)
        return project

    def load_project(self, project_id: str) -> Project:
        data = self._read_json(self.project_dir(project_id) / "project.json", None)
        if not data:
            raise FileNotFoundError(f"项目不存在: {project_id}")
        return Project.from_dict(data)

    def list_projects(self) -> list[Project]:
        base = self.data_root / "projects"
        if not base.exists():
            return []
        projects = []
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "project.json").exists():
                projects.append(Project.from_dict(self._read_json(child / "project.json", {})))
        return projects

    def require(self, project_id: str) -> Path:
        pdir = self.project_dir(project_id)
        if not (pdir / "project.json").exists():
            raise FileNotFoundError(f"项目不存在: {project_id}")
        return pdir

    # ---------- 材料 ----------
    def load_materials(self, project_id: str) -> list[Material]:
        rows = self._read_json(self.require(project_id) / "materials.json", [])
        return [Material.from_dict(r) for r in rows]

    def save_materials(self, project_id: str, materials: list[Material]) -> None:
        self._atomic_write_json(
            self.require(project_id) / "materials.json", [m.to_dict() for m in materials]
        )

    def next_id(self, project_id: str, prefix: str, existing: Iterable[str]) -> str:
        numbers = []
        for item in existing:
            match = re.fullmatch(rf"{prefix}-(\d+)", str(item))
            if match:
                numbers.append(int(match.group(1)))
        return f"{prefix}-{(max(numbers) + 1) if numbers else 1:03d}"

    # ---------- 观测 / 发现 / 状态 / 假设 / 实验候选 ----------
    def load_observations(self, project_id: str) -> list[Observation]:
        rows = self._read_json(self.require(project_id) / "observations.json", [])
        return [Observation.from_dict(r) for r in rows]

    def save_observations(self, project_id: str, observations: list[Observation]) -> None:
        self._atomic_write_json(
            self.require(project_id) / "observations.json", [o.to_dict() for o in observations]
        )

    def load_findings(self, project_id: str) -> list[Finding]:
        rows = self._read_json(self.require(project_id) / "findings.json", [])
        return [Finding.from_dict(r) for r in rows]

    def save_findings(self, project_id: str, findings: list[Finding]) -> None:
        self._atomic_write_json(self.require(project_id) / "findings.json", [f.to_dict() for f in findings])

    def load_state(self, project_id: str) -> ResearchState:
        data = self._read_json(self.require(project_id) / "research-state.json", {})
        return ResearchState.from_dict(data)

    def save_state(self, project_id: str, state: ResearchState) -> None:
        state.updated_at = now_iso()
        self._atomic_write_json(self.require(project_id) / "research-state.json", state.to_dict())

    def load_hypotheses(self, project_id: str) -> list[Hypothesis]:
        rows = self._read_json(self.require(project_id) / "hypotheses.json", [])
        return [Hypothesis.from_dict(r) for r in rows]

    def save_hypotheses(self, project_id: str, hypotheses: list[Hypothesis]) -> None:
        self._atomic_write_json(
            self.require(project_id) / "hypotheses.json", [h.to_dict() for h in hypotheses]
        )

    def load_candidates(self, project_id: str) -> list[ExperimentCandidate]:
        rows = self._read_json(self.require(project_id) / "experiments.json", [])
        return [ExperimentCandidate.from_dict(r) for r in rows]

    def save_candidates(self, project_id: str, candidates: list[ExperimentCandidate]) -> None:
        self._atomic_write_json(
            self.require(project_id) / "experiments.json", [c.to_dict() for c in candidates]
        )

    # ---------- 追加式台账 ----------
    def load_evidence_ledger(self, project_id: str) -> list[EvidenceEntry]:
        return [EvidenceEntry.from_dict(r) for r in self.read_jsonl(self.require(project_id) / "evidence-ledger.jsonl")]

    def append_evidence(self, project_id: str, entry: EvidenceEntry) -> EvidenceEntry:
        if not entry.id:
            existing = self.load_evidence_ledger(project_id)
            entry.id = self.next_id(project_id, "EV", [e.id for e in existing])
        if not entry.ts:
            entry.ts = now_iso()
        self.append_jsonl(self.require(project_id) / "evidence-ledger.jsonl", entry.to_dict())
        self.log_event(project_id, "evidence_appended", target=entry.id, detail=entry.summary[:200])
        return entry

    def load_decisions(self, project_id: str) -> list[DecisionRecord]:
        return [DecisionRecord.from_dict(r) for r in self.read_jsonl(self.require(project_id) / "decisions.jsonl")]

    def append_decision(self, project_id: str, decision: DecisionRecord) -> DecisionRecord:
        if not decision.id:
            decision.id = self.next_id(project_id, "D", [d.id for d in self.load_decisions(project_id)])
        if not decision.created_at:
            decision.created_at = now_iso()
        self.append_jsonl(self.require(project_id) / "decisions.jsonl", decision.to_dict())
        self.log_event(project_id, "decision_recorded", target=decision.id, detail=decision.action)
        return decision

    # ---------- 诊断报告 ----------
    def save_diagnosis_report(self, project_id: str, report: dict[str, Any], markdown: str) -> tuple[Path, Path]:
        base = self.require(project_id) / "diagnosis"
        existing = [p.name for p in base.glob("diag-*.json")] if base.exists() else []
        numbers = [int(p[5:-5]) for p in existing if p[5:-5].isdigit()]
        number = f"diag-{(max(numbers) + 1) if numbers else 1:03d}"
        base.mkdir(parents=True, exist_ok=True)
        json_path = base / f"{number}.json"
        md_path = base / f"{number}.md"
        self._atomic_write_json(json_path, report)
        md_path.write_text(markdown, encoding="utf-8")
        self.log_event(project_id, "diagnosis_written", target=number)
        return json_path, md_path
