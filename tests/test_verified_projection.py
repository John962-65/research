"""自由文本不会随数值检查被整体认证；已证实结果只取确定性事实投影。"""
from pathlib import Path

from research_copilot.analysis.evidence_validator import apply_validation, validate_finding
from research_copilot.core.evidence import sha256_file
from research_copilot.core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation, ResearchState
from research_copilot.core.research_state import sync_claims_from_findings


def test_established_results_do_not_copy_unverified_prose(tmp_path: Path):
    p = tmp_path / "d.csv"
    p.write_text("x\n8\n")
    m = Material("M", "results", str(p), sha256_file(p), "t")
    o = Observation("O", "均值为8", {"mean": 8}, [EvidenceRef("M", m.sha256)])
    f = Finding(id="F", statement="均值8，因此我的系统解决了所有科研难题", claim_type="statistical_finding", observation_ids=["O"], numeric_assertions=[NumericAssertion("mean", 8, check="mean")])
    # 该措辞不靠因果词检测也不能成为结果：结构化事实投影始终移除自由解释。
    f.statement = "均值8；我的系统解决了所有科研难题"
    v = validate_finding(f, {"O": o}, {"M": m})
    assert v["status"] == "verified"
    assert "解决了" in v["draft_statement"]
    assert "解决了" not in v["verified_statement"]
    apply_validation(f, v)
    state = ResearchState()
    sync_claims_from_findings(state, [f])
    assert "解决了" not in state.established_results[0]["statement"]
    assert "mean" in state.established_results[0]["statement"]
