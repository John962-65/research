from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.config import HumanConfig
from research_agent.human_brief import build_human_brief, render_human_brief_markdown, write_human_brief_artifacts


class HumanBriefTest(unittest.TestCase):
    def test_human_brief_builds_agent_context(self) -> None:
        report = build_human_brief(
            "机械臂路径规划",
            HumanConfig(
                notes=["优先关注窄通道场景"],
                constraints=["必须比较 RRT*"],
                success_criteria=["成功率提升且路径长度不恶化"],
                resource_limits=["只允许 smoke-first 本地运行"],
                risks=["避免只在玩具场景有效"],
            ),
        )
        rendered = render_human_brief_markdown(report)

        self.assertEqual(report["status"], "provided")
        self.assertIn("constraint: 必须比较 RRT*", report["agent_prompt_text"])
        self.assertIn("resource: 只允许 smoke-first 本地运行", report["agent_prompt_text"])
        self.assertIn("人工约束", rendered)
        self.assertIn("成功率提升", rendered)

    def test_empty_human_brief_is_explicit(self) -> None:
        report = build_human_brief("机械臂路径规划", HumanConfig())

        self.assertEqual(report["status"], "not_provided")
        self.assertEqual(report["agent_prompt_text"], "")
        self.assertTrue(report["warnings"])

    def test_writes_human_brief_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            report = write_human_brief_artifacts("机械臂路径规划", HumanConfig(constraints=["固定随机种子"]), out_dir)

            self.assertEqual(report["status"], "provided")
            self.assertTrue((out_dir / "00-human-brief.json").exists())
            self.assertTrue((out_dir / "00-human-brief.md").exists())


if __name__ == "__main__":
    unittest.main()
