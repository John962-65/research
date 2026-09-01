from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.idea_audit import build_idea_audit, render_idea_audit_markdown, write_idea_audit_artifacts
from research_agent.models import CitationEntry, ClaimSupport, EvidenceChunk, LiteratureContext, ResearchIdea, ReviewGate


class IdeaAuditTest(unittest.TestCase):
    def test_idea_audit_blocks_invalid_evidence_and_checks_constraints(self) -> None:
        context = _context()
        ideas = [
            _idea("无效证据分支", evidence_keys=["missing"], evidence_chunks=["bad-chunk"], baseline="RRT*"),
            _idea("覆盖人工约束分支", evidence_keys=["paper2024"], evidence_chunks=["paper2024-chunk-1"], baseline="RRT*"),
        ]
        constraints = {
            "constraints": [
                {"id": "RC01", "category": "baseline", "priority": "high", "text": "必须比较 RRT*"},
            ]
        }

        report = build_idea_audit("机械臂路径规划", ideas, context, review_constraints=constraints)
        rendered = render_idea_audit_markdown(report)

        self.assertEqual(report["status"], "review")
        self.assertEqual(report["blocked"], 1)
        self.assertEqual(report["pass"], 1)
        self.assertEqual(report["items"][0]["decision"], "block")
        self.assertIn("invalid citation keys", report["items"][0]["issues"][0])
        self.assertEqual(report["items"][1]["covered_constraints"], ["RC01"])
        self.assertIn("Idea 证据与约束审计", rendered)

    def test_write_idea_audit_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            report = write_idea_audit_artifacts(
                "机械臂路径规划",
                [_idea("可审计分支", evidence_keys=["paper2024"], evidence_chunks=["paper2024-chunk-1"], baseline="RRT*")],
                _context(),
                Path(tmp),
            )
            saved = json.loads((Path(tmp) / "02-idea-audit.json").read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertTrue((Path(tmp) / "02-idea-audit.md").exists())
            self.assertEqual(saved["items"][0]["decision"], "pass")


def _context() -> LiteratureContext:
    return LiteratureContext(
        topic="机械臂路径规划",
        citations=[
            CitationEntry(
                key="paper2024",
                title="RRT* for robot manipulator planning",
                authors=["A. Author"],
                year=2024,
                venue="Robotics",
                url="https://example.org/paper",
                doi="10.1234/example",
            )
        ],
        chunks=[
            EvidenceChunk(
                chunk_id="paper2024-chunk-1",
                citation_key="paper2024",
                title="RRT* for robot manipulator planning",
                text="RRT* baseline for robot manipulator motion planning.",
                source="test",
                url="https://example.org/paper",
                relevance=0.9,
            )
        ],
        claim_support=[
            ClaimSupport(
                claim="RRT* 是机械臂路径规划常用 baseline。",
                claim_type="baseline",
                support_level="supported",
                citation_keys=["paper2024"],
                evidence_notes=["baseline evidence"],
            )
        ],
        review_gate=ReviewGate(status="pass", warnings=[], required_actions=[]),
    )


def _idea(title: str, evidence_keys: list[str], evidence_chunks: list[str], baseline: str) -> ResearchIdea:
    return ResearchIdea(
        title=title,
        hypothesis=f"{title} 能提升路径规划评估可信度。",
        mechanism="对比 RRT* baseline 并分析失败模式。",
        expected_contribution="形成文献约束的机械臂路径规划实验协议。",
        novelty=4,
        feasibility=4,
        risk=2,
        evidence_keys=evidence_keys,
        evidence_chunks=evidence_chunks,
        gap_alignment="RRT* benchmark coverage",
        baseline=baseline,
        evaluation=["planning_success_rate", "collision_rate", "planning_time"],
        experiment_sketch=["构建任务集", "比较 candidate 与 RRT*", "统计失败模式"],
    )


if __name__ == "__main__":
    unittest.main()
