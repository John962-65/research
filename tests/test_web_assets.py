from __future__ import annotations

from pathlib import Path
import os
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebAssetsTest(unittest.TestCase):
    def test_llm_cost_fields_are_submitted_from_web_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="llm_input_cost_per_million_tokens"', index)
        self.assertIn('name="llm_output_cost_per_million_tokens"', index)
        self.assertIn("llm_input_cost_per_million_tokens", app)
        self.assertIn("llm_output_cost_per_million_tokens", app)

    def test_literature_query_fields_are_submitted_from_web_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="max_search_queries"', index)
        self.assertIn('name="extra_search_queries"', index)
        self.assertIn('name="semantic_scholar_api_key"', index)
        self.assertIn('name="openalex_api_key"', index)
        self.assertIn('name="literature_contact_email"', index)
        self.assertIn("max_search_queries", app)
        self.assertIn("extra_search_queries", app)
        self.assertIn("semantic_scholar_api_key", app)
        self.assertIn("openalex_api_key", app)
        self.assertIn("literature_contact_email", app)

    def test_paper_grade_flag_is_submitted_from_web_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="paper_grade_enabled"', index)
        self.assertIn("paper_grade_enabled", app)
        self.assertIn("form.get('paper_grade_enabled') === 'on'", app)

    def test_new_audit_stages_are_visible_in_stage_track(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("llm_trace_audit_completed", app)
        self.assertIn("run_economics_audit_completed", app)
        self.assertIn("llm_runtime_contract_completed", app)
        self.assertIn("agent_observability_audit_completed", app)
        self.assertIn("human_gate_audit_completed", app)
        self.assertIn("agent_stage_contract_completed", app)

    def test_literature_repair_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("literatureRetrievalGateLabel", app)
        self.assertIn("literatureRetrievalGateDetails", app)
        self.assertIn("literature_retrieval_gate", app)
        self.assertIn("检索门禁", app)
        self.assertIn("零返回 query", app)
        self.assertIn("限流来源", app)
        self.assertIn("legacy_summary", server)
        self.assertIn("_read_public_literature_retrieval_gate", server)
        self.assertIn('"literature_retrieval_gate": None', server)
        self.assertIn("literatureQualityGateLabel", app)
        self.assertIn("literatureQualityGateDetails", app)
        self.assertIn("literature_quality_gate", app)
        self.assertIn("文献门禁", app)
        self.assertIn("literatureEvidenceContractLabel", app)
        self.assertIn("literatureEvidenceContractDetails", app)
        self.assertIn("literature_evidence_contract", app)
        self.assertIn("证据契约", app)
        self.assertIn("实质证据片段", app)
        self.assertIn("substantive_chunk_coverage", app)
        self.assertIn("median_chunk_chars", app)
        self.assertIn("缺失角色", app)
        self.assertIn("Citation grounding", app)
        self.assertIn("RAG context", app)
        self.assertIn("LITERATURE_EVIDENCE_CONTRACT_JSON", server)
        self.assertIn("_read_public_literature_evidence_contract", server)
        self.assertIn("citations_with_substantive_chunks", server)
        self.assertIn("evidence_contract_substantive_chunk_coverage", server)
        self.assertIn("literature_gate_decision", server)
        self.assertIn("citation_grounding_status", server)
        self.assertIn("context_chunks", server)
        self.assertIn("LITERATURE_GATE_DECISION_JSON", server)
        self.assertIn("_read_public_literature_gate_decision", server)
        self.assertIn("literatureRepairLabel", app)
        self.assertIn("literature_search_feedback", app)
        self.assertIn("literature_search_strategy", app)
        self.assertIn("literatureRescuePlanLabel", app)
        self.assertIn("literature_rescue_plan", app)
        self.assertIn("literatureRescueExecutionLabel", app)
        self.assertIn("literature_rescue_execution", app)
        self.assertIn("检索修复", app)
        self.assertIn("补检索计划", app)
        self.assertIn("补检索执行", app)
        self.assertIn("批准进入 idea 前", app)

    def test_seed_intake_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("seedIntakeLabel", app)
        self.assertIn("seed_intake", app)
        self.assertIn("role_coverage_status", app)
        self.assertIn("missing_roles", app)
        self.assertIn("suggested_seed_count", app)
        self.assertIn("suggested_seed_role_counts", app)
        self.assertIn("!suggested", app)
        self.assertIn("/R", app)
        self.assertIn("Seed", app)

    def test_repair_resume_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("repairResumeLabel", app)
        self.assertIn("repair_resume_plan", app)
        self.assertIn("run.repair_resume_plan?.can_resume", app)
        self.assertIn("review_reapproval_required", app)
        self.assertIn("execution_reapproval_required", app)
        self.assertIn("修复恢复", app)

    def test_repair_resolution_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("repairResolutionLabel", app)
        self.assertIn("repair_resolution", app)
        self.assertIn("修复闭环", app)
        self.assertIn("_read_public_repair_resolution", server)
        self.assertIn("REPAIR_RESOLUTION_AUDIT_JSON", server)

    def test_repair_resume_preview_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="repair-resume-preview"', index)
        self.assertIn('id="apply-repair-resume"', index)
        self.assertIn("预览修复", index)
        self.assertIn("应用修复建议", index)
        self.assertIn("repairResumePreview", app)
        self.assertIn("applyRepairResume", app)
        self.assertIn("repairPreviewRunId", app)
        self.assertIn("repairPreviewPlan", app)
        self.assertIn("previewRepairResumeCurrentRun", app)
        self.assertIn("applyRepairResumePreviewToForm", app)
        self.assertIn("canApplyRepairResumePreview", app)
        self.assertIn("/repair-resume-preview", app)
        self.assertIn("preview_repair_resume", server)
        self.assertIn('"repair-resume-preview"', server)

    def test_repair_resume_preview_recommendations_can_be_applied_to_form(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("recommended_config", app)
        self.assertIn("recommended_execution_config", app)
        self.assertIn("recommended_paper_grade_config", app)
        self.assertIn("recommended_release_config", app)
        self.assertIn("releaseConfigValues", app)
        self.assertIn("releaseFormFieldByConfigKey", app)
        self.assertIn("retrieval_repair_tasks", app)
        self.assertIn("benchmark_manifest_paths", app)
        self.assertIn("setFieldValue('literature_provider'", app)
        self.assertIn("setFieldValue('literature_sources'", app)
        self.assertIn("setNumberMinimum('max_papers'", app)
        self.assertIn("setNumberMinimum('max_search_queries'", app)
        self.assertIn("appendTextareaLines('benchmark_manifests'", app)
        self.assertIn("ensureCommaListValue('allowed_commands'", app)
        self.assertIn("setFieldValue('execution_mode'", app)
        self.assertIn("setNumberMinimum('execution_repeats'", app)
        self.assertIn("setNumberMinimum('timeout_seconds'", app)
        self.assertIn("paperGrade.enabled === true", app)
        self.assertIn("paper_grade_enabled", app)
        self.assertIn("论文级门槛=开启", app)
        self.assertIn("不会批准 review gate 或执行 gate", app)
        self.assertIn("人工核对 seed、query、manifest", app)

    def test_run_integrity_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("runIntegrityLabel", app)
        self.assertIn("run_integrity", app)
        self.assertIn("完整性", app)

    def test_final_handoff_artifacts_are_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("final_handoff_completed", app)
        self.assertIn("finalHandoffLabel", app)
        self.assertIn("final_handoff", app)
        self.assertIn("package_zip_valid", app)
        self.assertIn("Z!", app)
        self.assertIn("14-final-handoff.md", index)
        self.assertIn("14-final-handoff.json", index)
        self.assertIn("最终交付", index)

    def test_benchmark_pack_run_artifacts_are_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("04-benchmark-pack-run.md", index)
        self.assertIn("04-benchmark-pack-run.json", index)
        self.assertIn("Benchmark Pack", index)
        self.assertIn('"04-benchmark-pack-run.md"', server)
        self.assertIn('"04-benchmark-pack-run.json"', server)

    def test_gold_run_doctor_artifacts_are_visible_as_public_summary(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("00-gold-run-doctor.md", index)
        self.assertIn("00-gold-launch-bundle.md", index)
        self.assertIn("00-gold-launch-bundle.json", index)
        self.assertIn("00-gold-launch-manifest.md", index)
        self.assertIn("00-gold-launch-manifest.json", index)
        self.assertIn("15-gold-run-verification.md", index)
        self.assertIn("15-gold-run-verification.json", index)
        self.assertIn("Gold Doctor", index)
        self.assertIn("Gold Bundle", index)
        self.assertIn("Gold Verify", index)
        self.assertIn("Gold 启动清单", index)
        self.assertIn("goldRunDoctorLabel", app)
        self.assertIn("goldRunVerifyLabel", app)
        self.assertIn("gold_run_doctor", app)
        self.assertIn("gold_run_verification", app)
        self.assertIn("gold_post_launch", server)
        self.assertIn("prelaunch_focus", app)
        self.assertIn("sk-[A-Za-z0-9_-]{8,}", app)
        self.assertIn("candidate_repair_resume_plan", app)
        self.assertIn("GOLD_RUN_DOCTOR_JSON", server)
        self.assertIn("GOLD_RUN_VERIFICATION_JSON", server)
        self.assertIn("GOLD_LAUNCH_BUNDLE_JSON", server)
        self.assertIn("prelaunch_focus", server)
        self.assertIn("sk-[A-Za-z0-9_-]{8,}", server)
        self.assertIn("GOLD_LAUNCH_MANIFEST_JSON", server)
        self.assertIn("_read_public_gold_run_doctor", server)
        self.assertIn("_read_public_gold_run_verification", server)
        self.assertIn("_read_public_gold_post_launch", server)
        self.assertIn("_read_public_gold_launch_bundle", server)
        self.assertIn("_read_public_gold_launch_manifest", server)
        self.assertIn("candidate_repair_resume_plan", server)

    def test_gold_server_environment_action_is_visible_in_gold_paths(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("goldEnvironmentActionMarkdown", app)
        self.assertIn("goldEnvironmentSafeCommands", app)
        self.assertIn("Server Environment Action", app)
        self.assertIn("hidden API key", app)
        self.assertIn("scripts/start_gold_web_env.sh", app)
        self.assertIn("scripts/run_gold_cli_env.sh", app)
        self.assertIn("ready_except_server_environment", app)
        self.assertGreaterEqual(app.count("goldEnvironmentActionMarkdown(result.report)"), 4)

    def test_agent_trajectory_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("agentTrajectoryLabel", app)
        self.assertIn("agent_trajectory", app)
        self.assertIn("轨迹", app)
        self.assertIn("last_event", app)
        self.assertIn("backfilled_events", app)
        self.assertIn("BF", app)
        self.assertIn("_read_public_agent_trajectory", server)
        self.assertIn('"agent_trajectory": None', server)
        self.assertIn("AGENT_TRAJECTORY_JSON", server)

    def test_agent_observability_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("agentObservabilityLabel", app)
        self.assertIn("agent_observability", app)
        self.assertIn("可观测", app)
        self.assertIn("manifest_events", app)
        self.assertIn("llm_budget_exceeded_calls", app)
        self.assertIn("_read_public_agent_observability", server)
        self.assertIn('"agent_observability": None', server)
        self.assertIn("AGENT_OBSERVABILITY_AUDIT_JSON", server)

    def test_human_gate_audit_summary_is_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("13-human-gate-audit.md", index)
        self.assertIn("13-human-gate-audit.json", index)
        self.assertIn("humanGateAuditLabel", app)
        self.assertIn("human_gate_audit", app)
        self.assertIn("人工Gate", app)
        self.assertIn("HUMAN_GATE_AUDIT_JSON", server)
        self.assertIn("_read_public_human_gate_audit", server)
        self.assertIn("repair_resume_applied", server)
        self.assertIn("review_reapproval_required", server)
        self.assertIn("execution_reapproval_required", server)

    def test_llm_runtime_contract_summary_is_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("13-llm-runtime-contract.md", index)
        self.assertIn("13-llm-runtime-contract.json", index)
        self.assertIn("llmRuntimeContractLabel", app)
        self.assertIn("llmObservabilityLabel", app)
        self.assertIn("llm_runtime_contract", app)
        self.assertIn("llm_observability", app)
        self.assertIn("LLM契约", app)
        self.assertIn("LLM总览", app)
        self.assertIn("missing_required_stage_count", app)
        self.assertIn("LLM_RUNTIME_CONTRACT_JSON", server)
        self.assertIn("_read_public_llm_runtime_contract", server)
        self.assertIn("_read_public_llm_observability_summary", server)
        self.assertIn("_public_llm_stage_ids", server)

    def test_literature_feedback_can_be_applied_to_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="apply-literature-feedback"', index)
        self.assertIn("applyLiteratureFeedbackToForm", app)
        self.assertIn("appendTextareaLines", app)
        self.assertIn("top_queries", app)
        self.assertIn("role_queries", app)
        self.assertIn("证据角色补检索 query", app)
        self.assertIn("unresolved_queries", app)
        self.assertIn("未闭环补检索 query", app)
        self.assertIn("role_repair_queries", app)
        self.assertIn("Seed 角色补检索 query", app)
        self.assertIn("suggested_seed_entries", app)
        self.assertIn("人工种子文献", app)
        self.assertIn("候选 DOI/URL 已写入人工种子文献", app)
        self.assertIn("max_papers>=12", app)
        self.assertIn("人工核对题名、年份和相关性", app)

    def test_run_memory_defaults_can_be_applied_to_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="apply-memory-defaults"', index)
        self.assertIn("应用历史推荐", index)
        self.assertIn("applyMemoryDefaults", app)
        self.assertIn("applyMemoryDefaultsToForm", app)
        self.assertIn("result.memory?.recommended_config", app)
        self.assertIn("setFieldValue('literature_provider'", app)
        self.assertIn("setFieldValue('literature_sources'", app)
        self.assertIn("setNumberMinimum('max_papers'", app)
        self.assertIn("setNumberMinimum('max_search_queries'", app)
        self.assertIn("appendTextareaLines('extra_search_queries'", app)
        self.assertIn("manual_seed_required", app)
        self.assertIn("release_required_fields", app)
        self.assertIn("release_recommended_fields", app)
        self.assertIn("release_cli_args", app)
        self.assertIn("missingReleaseFormFields", app)
        self.assertIn("Release 必填仍需人工填写", app)
        self.assertIn("CLI 等价参数", app)
        self.assertIn("不会启动研究、批准 review gate 或执行 gate", app)
        self.assertIn("els.applyMemoryDefaults.addEventListener('click', applyMemoryDefaultsToForm)", app)

    def test_literature_preview_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="literature-preview"', index)
        self.assertIn('id="paper-grade-probe"', index)
        self.assertIn('id="apply-literature-preview-seeds"', index)
        self.assertIn("预览文献", index)
        self.assertIn("Gold 文献 Probe", index)
        self.assertIn("应用预览 Seed", index)
        self.assertIn("literaturePreview", app)
        self.assertIn("paperGradeProbe", app)
        self.assertIn("literaturePreviewReport", app)
        self.assertIn("applyLiteraturePreviewSeeds", app)
        self.assertIn("applyLiteraturePreviewSeedsToForm", app)
        self.assertIn("recommended_seed_entries", app)
        self.assertIn("seed_role_coverage", app)
        self.assertIn("role_counts", app)
        self.assertIn("missing_roles", app)
        self.assertIn("预览 Seed 角色覆盖", app)
        self.assertIn("appendTextareaLines('seed_papers'", app)
        self.assertIn("report.topic", app)
        self.assertIn("不会启动研究、批准 review gate 或进入 idea/实验", app)
        self.assertIn("previewLiterature", app)
        self.assertIn("runPaperGradeProbe", app)
        self.assertIn("/api/literature-preview", app)
        self.assertIn("/api/paper-grade-probe", app)
        self.assertIn("文献预览失败", app)
        self.assertIn("Gold 文献 Probe 失败", app)
        probe_start = app.index("async function runPaperGradeProbe()")
        probe_end = app.index("function applyLiteraturePreviewSeedsToForm()", probe_start)
        probe_js = app[probe_start:probe_end]
        self.assertIn("delete payload.llm_api_key", probe_js)
        self.assertIn("delete payload.semantic_scholar_api_key", probe_js)
        self.assertIn("delete payload.openalex_api_key", probe_js)
        self.assertIn("els.literaturePreview.addEventListener('click', previewLiterature)", app)
        self.assertIn("els.paperGradeProbe.addEventListener('click', runPaperGradeProbe)", app)
        self.assertIn("els.applyLiteraturePreviewSeeds.addEventListener('click', applyLiteraturePreviewSeedsToForm)", app)
        self.assertIn('parsed.path == "/api/literature-preview"', server)
        self.assertIn('parsed.path == "/api/paper-grade-probe"', server)
        self.assertIn("_handle_paper_grade_probe", server)
        self.assertIn("_public_paper_grade_probe_report", server)
        self.assertIn("_literature_preview_report", server)
        self.assertIn("_literature_preview_seed_items", server)
        self.assertIn("recommended_seed_entries", server)
        self.assertIn("recommended_seed_items", server)
        self.assertIn("seed_role_coverage", server)
        self.assertIn("_literature_preview_paper_roles", server)
        self.assertIn("_render_literature_preview_markdown", server)
        self.assertIn("不创建 run、不批准 review gate、不进入 idea/实验、不调用 LLM", server)

    def test_run_library_search_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="library-query"', index)
        self.assertIn('id="library-search"', index)
        self.assertIn("loadRunLibrary", app)
        self.assertIn("/api/library", app)
        self.assertIn("libraryQuery", app)
        self.assertIn("librarySearch", app)
        self.assertIn('parsed.path == "/api/library"', server)
        self.assertIn("build_run_library", server)

    def test_platform_audit_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="platform-audit"', index)
        self.assertIn("平台审计", index)
        self.assertIn("platformAudit", app)
        self.assertIn("loadPlatformAudit", app)
        self.assertIn("/api/platform-audit", app)
        self.assertIn("runs-platform-audit", app)
        self.assertIn('parsed.path == "/api/platform-audit"', server)
        audit_handler_start = server.index('if parsed.path == "/api/platform-audit":')
        audit_handler_end = server.index('if parsed.path == "/api/perfect-readiness":', audit_handler_start)
        audit_handler = server[audit_handler_start:audit_handler_end]
        self.assertIn("build_platform_audit", audit_handler)
        self.assertIn("render_platform_audit_markdown", audit_handler)
        self.assertNotIn("write_platform_audit", audit_handler)

    def test_perfect_readiness_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="perfect-readiness"', index)
        self.assertIn("完美度", index)
        self.assertIn("perfectReadiness", app)
        self.assertIn("loadPerfectReadiness", app)
        self.assertIn("/api/perfect-readiness", app)
        self.assertIn('parsed.path == "/api/perfect-readiness"', server)
        self.assertIn("write_perfect_agent_readiness_artifacts", server)
        self.assertIn("render_perfect_agent_readiness_markdown", server)

    def test_open_source_compliance_backfill_buttons_are_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="open-source-backfill-preview"', index)
        self.assertIn('id="open-source-backfill-run"', index)
        self.assertIn("预览回填", index)
        self.assertIn("执行回填", index)
        self.assertIn("openSourceBackfillPreview", app)
        self.assertIn("openSourceBackfillRun", app)
        self.assertIn("openSourceComplianceLabel", app)
        self.assertIn("open_source_compliance", app)
        self.assertIn("开源 ${summary.status}", app)
        self.assertIn("previewOpenSourceBackfill", app)
        self.assertIn("runOpenSourceBackfill", app)
        self.assertIn("/api/open-source-compliance-backfill", app)
        self.assertIn("没有启动研究、批准 review gate 或执行实验", app)
        self.assertIn('parsed.path == "/api/open-source-compliance-backfill"', server)
        self.assertIn("backfill_open_source_compliance", server)
        self.assertIn("_read_public_open_source_compliance", server)
        self.assertIn("blocking_issue_count", server)
        self.assertIn("blocked_project_count", server)

    def test_llm_observability_backfill_buttons_are_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="llm-backfill-preview"', index)
        self.assertIn('id="llm-backfill-run"', index)
        self.assertIn("预览 LLM", index)
        self.assertIn("回填 LLM审计", index)
        self.assertIn("llmBackfillPreview", app)
        self.assertIn("llmBackfillRun", app)
        self.assertIn("previewLlmObservabilityBackfill", app)
        self.assertIn("runLlmObservabilityBackfill", app)
        self.assertIn("/api/llm-observability-backfill", app)
        self.assertIn("没有创建 LLM 账本、启动研究、批准 review gate 或执行实验", app)
        self.assertIn('parsed.path == "/api/llm-observability-backfill"', server)
        self.assertIn("backfill_llm_observability", server)

    def test_repair_resume_backfill_buttons_are_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="repair-backfill-preview"', index)
        self.assertIn('id="repair-backfill-run"', index)
        self.assertIn("预览修复回填", index)
        self.assertIn("回填修复预案", index)
        self.assertIn("repairBackfillPreview", app)
        self.assertIn("repairBackfillRun", app)
        self.assertIn("previewRepairResumeBackfill", app)
        self.assertIn("runRepairResumeBackfill", app)
        self.assertIn("/api/repair-resume-backfill", app)
        self.assertIn("没有删除产物、恢复 pipeline、批准 gate 或执行实验", app)
        self.assertIn('parsed.path == "/api/repair-resume-backfill"', server)
        self.assertIn("backfill_repair_resume_plans", server)
        self.assertIn("_public_repair_resume_backfill_report", server)

    def test_repair_resume_backlog_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="repair-backlog"', index)
        self.assertIn("修复 Backlog", index)
        self.assertIn("repairBacklog", app)
        self.assertIn("loadRepairResumeBacklog", app)
        self.assertIn("/api/repair-resume-backlog", app)
        self.assertIn("只读取修复 backlog", app)
        self.assertIn("没有删除产物、批准 gate、恢复 pipeline 或执行实验", app)
        self.assertIn('parsed.path == "/api/repair-resume-backlog"', server)
        self.assertIn("build_repair_resume_backlog", server)
        self.assertIn("_public_repair_resume_backlog_report", server)

    def test_prior_run_library_artifacts_are_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("00-prior-run-library.md", index)
        self.assertIn("00-prior-run-library.json", index)
        self.assertIn("历史成果", index)
        self.assertIn("PRIOR_RUN_LIBRARY_JSON", server)
        self.assertIn("PRIOR_RUN_LIBRARY_MD", server)

    def test_experiment_manager_artifacts_are_visible(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("实验管理", index)
        self.assertIn("02-experiment-manager.md", index)
        self.assertIn("02-experiment-manager.json", index)
        self.assertIn("experimentManagerLabel", app)
        self.assertIn("experiment_manager", app)
        self.assertIn("queue_blocked", app)
        self.assertIn("queue_human_review", app)
        self.assertIn("queue_ready_backlog", app)
        self.assertIn("queue_summary", server)
        self.assertIn('"queue_blocks_current_experiment"', server)

    def test_idea_experiment_gate_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("ideaExperimentGateLabel", app)
        self.assertIn("ideaExperimentGateDetails", app)
        self.assertIn("idea_experiment_gate", app)
        self.assertIn("Idea/实验门禁", app)
        self.assertIn("批准执行前", app)
        self.assertIn("_read_public_idea_experiment_gate", server)
        self.assertIn('"idea_experiment_gate": None', server)

    def test_benchmark_preview_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn('id="benchmark-preview"', index)
        self.assertIn('id="benchmark-template"', index)
        self.assertIn('id="benchmark-manifest-lint"', index)
        self.assertIn('id="benchmark-manifest-save"', index)
        self.assertIn('id="benchmark-manifest-draft-path"', index)
        self.assertIn('id="benchmark-manifest-draft"', index)
        self.assertIn('id="apply-benchmark-example"', index)
        self.assertIn('id="release-metadata-lint"', index)
        self.assertIn("benchmarks/**/manifest.json", index)
        self.assertIn("previewBenchmark", app)
        self.assertIn("showBenchmarkTemplate", app)
        self.assertIn("lintBenchmarkManifestDraft", app)
        self.assertIn("saveBenchmarkManifestDraft", app)
        self.assertIn("lintReleaseMetadata", app)
        self.assertIn("benchmarkManifestDraftPayload", app)
        self.assertIn("applyBenchmarkExampleToForm", app)
        self.assertIn("/api/benchmark-preview", app)
        self.assertIn("/api/benchmark-template", app)
        self.assertIn("/api/benchmark-manifest-lint", app)
        self.assertIn("/api/benchmark-manifest-save", app)
        self.assertIn("/api/benchmark-examples", app)
        self.assertIn("/api/release-metadata-lint", app)
        self.assertIn("benchmarkPreview", app)
        self.assertIn("benchmarkTemplate", app)
        self.assertIn("benchmarkManifestLint", app)
        self.assertIn("benchmarkManifestSave", app)
        self.assertIn("benchmarkManifestDraftPath", app)
        self.assertIn("benchmarkManifestDraft", app)
        self.assertIn("releaseMetadataLint", app)
        self.assertIn("ensureCommaListValue", app)
        self.assertIn("appendTextareaLines('benchmark_manifests'", app)
        self.assertIn('parsed.path == "/api/benchmark-template"', server)
        self.assertIn('parsed.path == "/api/benchmark-manifest-lint"', server)
        self.assertIn('parsed.path == "/api/benchmark-manifest-save"', server)
        self.assertIn('parsed.path == "/api/release-metadata-lint"', server)
        self.assertIn("_benchmark_template", server)
        self.assertIn("_lint_benchmark_manifest_payload", server)
        self.assertIn("_benchmark_manifest_save_path", server)
        self.assertIn("_handle_release_metadata_lint", server)

    def test_gold_run_doctor_button_is_wired(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")
        gold_doctor_start = app.index("async function runGoldDoctor()")
        gold_doctor_end = app.index("async function previewLiterature()", gold_doctor_start)
        gold_doctor_js = app[gold_doctor_start:gold_doctor_end]

        self.assertIn('id="gold-run-doctor"', index)
        self.assertIn('id="env-llm-preflight"', index)
        self.assertIn('id="gold-env-lint"', index)
        self.assertIn('id="gold-env-launch-kit"', index)
        self.assertIn('id="gold-launch-bundle"', index)
        self.assertIn('id="gold-run-launch"', index)
        self.assertIn('id="gold-run-verify"', index)
        self.assertIn('id="apply-gold-defaults"', index)
        self.assertIn('id="gold-defaults-smoke"', index)
        self.assertIn('name="benchmark_pack_run_dir"', index)
        self.assertIn('name="fulltext_grounding_run_dir"', index)
        self.assertIn('id="gold-launch-command-panel"', index)
        self.assertIn('id="gold-launch-checklist"', index)
        self.assertIn('id="gold-launch-command-text"', index)
        self.assertIn('id="copy-gold-launch-commands"', index)
        self.assertIn("Safe Launch Commands", index)
        self.assertIn("goldRunDoctor", app)
        self.assertIn("envLlmPreflight", app)
        self.assertIn("goldEnvLint", app)
        self.assertIn("goldEnvLaunchKit", app)
        self.assertIn("goldLaunchBundle", app)
        self.assertIn("goldRunLaunch", app)
        self.assertIn("goldRunVerify", app)
        self.assertIn("goldVerifyFollowupLines", app)
        self.assertIn("applyGoldDefaults", app)
        self.assertIn("goldDefaultsSmoke", app)
        self.assertIn("runGoldDoctor", app)
        self.assertIn("runGoldLaunch", app)
        gold_launch_start = app.index("async function runGoldLaunch()")
        gold_launch_end = app.index("async function runGoldDoctor()", gold_launch_start)
        gold_launch_js = app[gold_launch_start:gold_launch_end]
        self.assertIn("reports?.gold_env?.server_environment", gold_launch_js)
        self.assertIn("required_present", gold_launch_js)
        self.assertIn("required_total", gold_launch_js)
        self.assertIn("gateway_socket", gold_launch_js)
        self.assertIn("env: ${envPresent}/${envTotal}", gold_launch_js)
        self.assertIn("gateway: ${gatewayStatus}", gold_launch_js)
        self.assertIn("post_launch_guidance?.commands", gold_launch_js)
        self.assertIn("runGoldVerify", app)
        self.assertIn("runGoldDefaultsSmoke", app)
        gold_defaults_start = app.index("async function runGoldDefaultsSmoke()")
        gold_defaults_end = app.index("async function loadRunLibrary()", gold_defaults_start)
        gold_defaults_js = app[gold_defaults_start:gold_defaults_end]
        self.assertIn("server_environment", gold_defaults_js)
        self.assertIn("required_present", gold_defaults_js)
        self.assertIn("required_total", gold_defaults_js)
        self.assertIn("gateway_socket", gold_defaults_js)
        self.assertIn("env: ${envPresent}/${envTotal}", gold_defaults_js)
        self.assertIn("gateway: ${gatewayStatus}", gold_defaults_js)
        self.assertIn("runEnvLlmPreflight", app)
        self.assertIn("lintGoldEnv", app)
        self.assertIn("showGoldEnvLaunchKit", app)
        gold_env_kit_start = app.index("async function showGoldEnvLaunchKit()")
        gold_env_kit_end = app.index("async function runGoldLaunchBundle()", gold_env_kit_start)
        gold_env_kit_js = app[gold_env_kit_start:gold_env_kit_end]
        self.assertIn("server_environment", gold_env_kit_js)
        self.assertIn("required_present", gold_env_kit_js)
        self.assertIn("required_total", gold_env_kit_js)
        self.assertIn("gateway_socket", gold_env_kit_js)
        self.assertIn("env: ${envPresent}/${envTotal}", gold_env_kit_js)
        self.assertIn("gateway: ${gatewayStatus}", gold_env_kit_js)
        self.assertIn("runGoldLaunchBundle", app)
        self.assertIn("applyGoldDefaultsToForm", app)
        self.assertIn("/api/gold-defaults", app)
        self.assertIn("benchmark_pack_run_dir", app)
        self.assertIn("fulltext_grounding_run_dir", app)
        self.assertIn("supportRuns.benchmark_pack_run_dir", app)
        self.assertIn("releaseConfigValues(release)", app)
        self.assertIn("literature.seed_papers", app)
        self.assertIn("appendTextareaLines('seed_papers'", app)
        self.assertIn("appendTextareaLines('fulltext_paths'", app)
        self.assertIn("appendTextareaLines('extra_search_queries'", app)
        self.assertIn("textareaLines('benchmark_manifests')", app)
        self.assertIn("正式 Benchmark Manifest", app)
        self.assertIn("/api/env-llm-preflight", app)
        self.assertIn("/api/gold-env-lint", app)
        self.assertIn("/api/gold-env-launch-kit", app)
        self.assertIn("/api/gold-launch-bundle", app)
        self.assertIn("/api/gold-run-launch", app)
        self.assertIn("/api/gold-run-verify", app)
        self.assertIn("JSON.stringify({candidate_run_id: state.currentRun.id})", app)
        self.assertIn("await refreshRuns(true)", app)
        self.assertIn("wrote_artifacts", app)
        self.assertIn("perfect_readiness_written", app)
        self.assertIn("repair_resume_plan", app)
        self.assertIn("delete payload.llm_api_key", app)
        self.assertIn("delete payload.semantic_scholar_api_key", app)
        self.assertIn("delete payload.openalex_api_key", app)
        self.assertIn("delete payload.llm_api_key", gold_doctor_js)
        self.assertIn("delete payload.semantic_scholar_api_key", gold_doctor_js)
        self.assertIn("delete payload.openalex_api_key", gold_doctor_js)
        gold_env_start = app.index("async function lintGoldEnv()")
        gold_env_end = app.index("async function runGoldDoctor()", gold_env_start)
        gold_env_js = app[gold_env_start:gold_env_end]
        self.assertIn("delete payload.llm_api_key", gold_env_js)
        self.assertIn("delete payload.semantic_scholar_api_key", gold_env_js)
        self.assertIn("delete payload.openalex_api_key", gold_env_js)
        self.assertIn("async function showGoldEnvLaunchKit()", gold_env_js)
        gold_bundle_start = app.index("async function runGoldLaunchBundle()")
        gold_bundle_end = app.index("async function runGoldDoctor()", gold_bundle_start)
        gold_bundle_js = app[gold_bundle_start:gold_bundle_end]
        self.assertIn("delete payload.llm_api_key", gold_bundle_js)
        self.assertIn("delete payload.semantic_scholar_api_key", gold_bundle_js)
        self.assertIn("delete payload.openalex_api_key", gold_bundle_js)
        self.assertIn("renderGoldLaunchChecklist(result.report?.components)", gold_bundle_js)
        self.assertIn("launch_plan", server)
        self.assertIn("_gold_bundle_launch_plan", server)
        self.assertIn("launch_status", app)
        self.assertIn("can_start_gold_run", app)
        self.assertIn("publicGoldLaunchReadiness", app)
        self.assertIn("launch_manifest", app)
        self.assertIn("launch_readiness", app)
        self.assertIn("launch_markdown", app)
        self.assertIn("renderGoldLaunchChecklist(result.launch_manifest?.launch_checklist)", app)
        self.assertIn("publicGoldLaunchChecklist", app)
        self.assertIn("safeLaunchText", app)
        self.assertIn("result.launch_manifest?.launch_readiness", app)
        self.assertIn("renderGoldLaunchCommands(result.launch_commands)", app)
        self.assertIn("publicGoldLaunchCommands", app)
        self.assertIn("copyGoldLaunchCommands", app)
        self.assertIn("clearGoldLaunchCommandsWhenArtifactChanges", app)
        self.assertIn("sk-<redacted>", app)
        self.assertIn("MutationObserver", app)
        self.assertIn("launch-command-panel", styles)
        self.assertIn("launch-checklist", styles)
        self.assertIn(".launch-checklist-status.review", styles)
        self.assertIn("launch_commands", server)
        self.assertIn("launch_command_markdown", server)
        self.assertIn("launch_readiness", server)
        self.assertIn("launch_checklist", server)
        self.assertIn("_public_launch_readiness", server)
        self.assertIn("_public_launch_checklist", server)
        self.assertIn('parsed.path == "/api/env-llm-preflight"', server)
        self.assertIn('parsed.path == "/api/gold-env-lint"', server)
        self.assertIn('parsed.path == "/api/gold-env-launch-kit"', server)
        self.assertIn('parsed.path == "/api/gold-launch-bundle"', server)
        self.assertIn('parsed.path == "/api/gold-run-launch"', server)
        self.assertIn('parsed.path == "/api/gold-run-verify"', server)
        self.assertIn("_handle_env_llm_preflight", server)
        self.assertIn("_handle_gold_env_lint", server)
        self.assertIn("_handle_gold_env_launch_kit", server)
        self.assertIn("_handle_gold_launch_bundle", server)
        self.assertIn("_handle_gold_run_launch", server)
        self.assertIn("_handle_gold_run_verify", server)
        self.assertIn("build_gold_launch_bundle_report", server)
        self.assertIn("write_gold_run_verification_artifacts", server)
        self.assertIn("_write_gold_verification_followups", server)
        self.assertIn("write_repair_resume_plan_artifacts", server)
        self.assertIn("write_perfect_agent_readiness_artifacts", server)
        self.assertIn("_write_gold_verification_if_gold_launch", server)
        self.assertIn("_env_llm_config_from_payload", server)
        self.assertIn("_live_gold_launch_commands", server)
        self.assertIn("_render_live_gold_launch_commands_markdown", server)
        self.assertIn('parsed.path == "/api/gold-defaults"', server)
        self.assertIn('parsed.path == "/api/gold-defaults-smoke"', server)
        self.assertIn("_gold_defaults", server)
        self.assertIn("build_gold_defaults_smoke_report", server)
        self.assertIn("render_gold_defaults_smoke_markdown", server)
        self.assertIn("_gold_default_benchmark_pack", server)
        self.assertIn("build_gold_env_launch_kit", server)
        self.assertIn("render_gold_env_launch_kit_markdown", server)
        self.assertIn("cli_launcher_command", server)
        self.assertIn("post_key_doctor_ping_and_bundle_gate", server)
        self.assertIn("helper_script_post_key_checks", server)
        self.assertIn("scripts/run_gold_cli_env.sh", server)
        self.assertIn("/api/gold-run-doctor", app)
        self.assertIn('parsed.path == "/api/gold-run-doctor"', server)
        self.assertIn("_handle_gold_run_doctor", server)

    def test_gold_web_env_script_is_safe_and_documented(self) -> None:
        script = (ROOT / "scripts" / "start_gold_web_env.sh").read_text(encoding="utf-8")
        cli_script = (ROOT / "scripts" / "run_gold_cli_env.sh").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("read -rsp", script)
        self.assertIn("OPENAI_BASE_URL", script)
        self.assertIn("http://127.0.0.1:8317", script)
        self.assertIn("gpt-5.5", script)
        self.assertIn('export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"', script)
        self.assertIn("resolve_python_bin", script)
        self.assertIn("RESEARCH_AGENT_PYTHON_BIN", script)
        self.assertIn("sys.version_info >= (3, 11)", script)
        self.assertIn('exec "$PYTHON_BIN" -m research_agent.web_server', script)
        self.assertIn("ensure_web_port_available", script)
        self.assertIn("ensure_llm_gateway_reachable", script)
        self.assertIn("RESEARCH_AGENT_WEB_REPLACE", script)
        self.assertIn("RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK", script)
        self.assertIn("RESEARCH_AGENT_OPENAI_API_KEY_FIFO", script)
        self.assertIn("read_secret_from_fifo", script)
        self.assertIn("mkfifo -m 600", readme)
        self.assertIn("Aborted before reading OPENAI_API_KEY", script)
        self.assertIn("stdin is not interactive", script)
        self.assertIn("%s is required", script)
        self.assertIn("valid_contact_email", script)
        self.assertIn("gold-defaults-smoke", script)
        self.assertIn("gold-run-doctor", script)
        self.assertIn("--ping-llm", script)
        self.assertIn("gold-launch-bundle", script)
        self.assertIn("RESEARCH_AGENT_GOLD_LLM_TIMEOUT_SECONDS", script)
        self.assertIn("prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL", script)
        self.assertIn("prompt_required_secret OPENAI_API_KEY", script)
        self.assertLess(script.index("prompt_required_secret OPENAI_API_KEY"), script.index("gold-run-doctor"))
        self.assertLess(script.index("gold-run-doctor"), script.index("gold-launch-bundle"))
        self.assertLess(script.index("gold-launch-bundle"), script.index('exec "$PYTHON_BIN" -m research_agent.web_server'))
        self.assertLess(script.index("ensure_web_port_available"), script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(script.index("ensure_llm_gateway_reachable"), script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(script.index("prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL"), script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(script.index("gold-defaults-smoke"), script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertNotIn("sk-", script)
        self.assertIn("scripts/start_gold_web_env.sh", readme)
        self.assertIn("scripts/run_gold_cli_env.sh", readme)
        self.assertIn("隐藏输入读取 API key", readme)
        self.assertIn("先校验真实 contact email", readme)
        self.assertIn("随后先运行只读 `gold-defaults-smoke`", readme)
        self.assertIn("最后才用隐藏输入读取 `OPENAI_API_KEY`", readme)
        self.assertIn("RESEARCH_AGENT_OPENAI_API_KEY_FIFO", readme)
        self.assertIn("脚本都会在读取 API key 之前退出", readme)
        self.assertIn("read -rsp", cli_script)
        self.assertIn('export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"', cli_script)
        self.assertIn("resolve_python_bin", cli_script)
        self.assertIn("RESEARCH_AGENT_PYTHON_BIN", cli_script)
        self.assertIn("sys.version_info >= (3, 11)", cli_script)
        self.assertIn("valid_contact_email", cli_script)
        self.assertIn("RESEARCH_AGENT_OPENAI_API_KEY_FIFO", cli_script)
        self.assertIn("read_secret_from_fifo", cli_script)
        self.assertIn("prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL", cli_script)
        self.assertIn("prompt_required_secret OPENAI_API_KEY", cli_script)
        self.assertIn("ensure_llm_gateway_reachable", cli_script)
        self.assertIn("Aborted before reading OPENAI_API_KEY", cli_script)
        self.assertIn("stdin is not interactive", cli_script)
        self.assertIn("not reachable before reading OPENAI_API_KEY", cli_script)
        self.assertIn("gold-defaults-smoke", cli_script)
        self.assertIn("gold-run-doctor", cli_script)
        self.assertIn("--ping-llm", cli_script)
        self.assertIn("gold-launch-bundle", cli_script)
        self.assertIn("gold-run-launch", cli_script)
        self.assertIn('gold-run-verify --run-dir "$OUT_DIR"', cli_script)
        self.assertIn("perfect-readiness --project-dir . --runs-dir", cli_script)
        self.assertIn('repair-resume "$OUT_DIR" --dry-run --gold-run-verification-report "$OUT_DIR/15-gold-run-verification.json"', cli_script)
        self.assertIn("run_gold_launch_with_final_audit", cli_script)
        self.assertIn("launch_status=$?", cli_script)
        self.assertIn("audit_status=$?", cli_script)
        self.assertIn('if [[ -d "$OUT_DIR" ]]; then', cli_script)
        self.assertIn('return "$launch_status"', cli_script)
        self.assertIn("RESEARCH_AGENT_GOLD_CONFIRM", cli_script)
        self.assertIn("RESEARCH_AGENT_GOLD_DRY_RUN", cli_script)
        self.assertIn("RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK", cli_script)
        self.assertLess(cli_script.index("Aborted before reading OPENAI_API_KEY"), cli_script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(cli_script.index("ensure_llm_gateway_reachable"), cli_script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(cli_script.index("prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL"), cli_script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(cli_script.index("gold-defaults-smoke"), cli_script.index("prompt_required_secret OPENAI_API_KEY"))
        self.assertLess(cli_script.index("gold-defaults-smoke"), cli_script.index("gold-launch-bundle"))
        self.assertLess(cli_script.index("gold-run-doctor"), cli_script.index("gold-launch-bundle"))
        self.assertLess(cli_script.index("gold-launch-bundle"), cli_script.rindex("run_gold_launch_with_final_audit"))
        self.assertLess(
            cli_script.index('"$PYTHON_BIN" -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR"'),
            cli_script.index("run_final_gold_audits", cli_script.index('"$PYTHON_BIN" -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR"')),
        )
        self.assertNotIn("sk-", cli_script)

    def test_gold_env_scripts_fail_loudly_without_interactive_stdin(self) -> None:
        env = {
            **os.environ,
            "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK": "1",
            "RESEARCH_AGENT_GOLD_DRY_RUN": "1",
            "RESEARCH_AGENT_WEB_PORT": "0",
        }
        for key in ["OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]:
            env.pop(key, None)

        cli = subprocess.run(
            ["scripts/run_gold_cli_env.sh"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )
        web = subprocess.run(
            ["scripts/start_gold_web_env.sh"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )

        for completed in [cli, web]:
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("RESEARCH_AGENT_CONTACT_EMAIL is required but stdin is not interactive", completed.stderr)
            self.assertIn("Aborted before reading OPENAI_API_KEY", completed.stderr)
            self.assertNotIn("OPENAI_API_KEY:", completed.stderr)
            self.assertNotIn("sk-", completed.stderr)

    def test_gold_env_scripts_reject_unsupported_python_before_reading_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            old_python = Path(tmp) / "python-old"
            old_python.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            old_python.chmod(0o755)
            env = {
                **os.environ,
                "RESEARCH_AGENT_PYTHON_BIN": str(old_python),
                "OPENAI_API_KEY": "unit-test-token",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
            }
            for script_name in ["scripts/run_gold_cli_env.sh", "scripts/start_gold_web_env.sh"]:
                completed = subprocess.run(
                    [script_name],
                    cwd=ROOT,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertIn("requires Python 3.11 or newer", completed.stderr)
                self.assertIn("RESEARCH_AGENT_PYTHON_BIN", completed.stderr)
                self.assertNotIn("unit-test-token", completed.stdout + completed.stderr)

    def test_gold_env_scripts_reject_placeholder_contact_email_before_secret(self) -> None:
        env = {
            **os.environ,
            "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK": "1",
            "RESEARCH_AGENT_GOLD_DRY_RUN": "1",
            "RESEARCH_AGENT_WEB_PORT": "0",
            "RESEARCH_AGENT_CONTACT_EMAIL": "agent@example.org",
        }
        env.pop("OPENAI_API_KEY", None)

        cli = subprocess.run(
            ["scripts/run_gold_cli_env.sh"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )
        web = subprocess.run(
            ["scripts/start_gold_web_env.sh"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )

        for completed in [cli, web]:
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("RESEARCH_AGENT_CONTACT_EMAIL must be a real contact email", completed.stderr)
            self.assertIn("Aborted before reading OPENAI_API_KEY", completed.stderr)
            self.assertNotIn("OPENAI_API_KEY:", completed.stderr)
            self.assertNotIn("agent@example.org", completed.stderr)
            self.assertNotIn("sk-", completed.stderr)

    def test_gold_web_env_script_runs_doctor_and_bundle_before_web_server(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "python-calls.log"
            mock_bin = tmp_path / "bin"
            mock_bin.mkdir()
            mock_python = mock_bin / "python3"
            mock_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf 'PYTHONPATH=%s\\n' "${PYTHONPATH:-}" >> "$RESEARCH_AGENT_TEST_PYTHON_LOG"
printf '%s\\n' "$*" >> "$RESEARCH_AGENT_TEST_PYTHON_LOG"
exit 0
""",
                encoding="utf-8",
            )
            mock_python.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{mock_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONPATH": "preexisting-pythonpath",
                "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK": "1",
                "RESEARCH_AGENT_WEB_PORT": "0",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                "OPENAI_API_KEY": "unit-test-token",
                "RESEARCH_AGENT_PYTHON_BIN": str(mock_python),
                "RESEARCH_AGENT_TEST_PYTHON_LOG": str(log_path),
            }
            completed = subprocess.run(
                ["scripts/start_gold_web_env.sh"],
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
            )
            calls = log_path.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"PYTHONPATH={ROOT / 'src'}:preexisting-pythonpath", calls)
        self.assertIn("research_agent gold-defaults-smoke", calls)
        self.assertIn("research_agent gold-run-doctor", calls)
        self.assertIn("--ping-llm", calls)
        self.assertIn("research_agent gold-launch-bundle", calls)
        self.assertIn("research_agent.web_server", calls)
        self.assertLess(calls.index("research_agent gold-defaults-smoke"), calls.index("research_agent gold-run-doctor"))
        self.assertLess(calls.index("research_agent gold-run-doctor"), calls.index("research_agent gold-launch-bundle"))
        self.assertLess(calls.index("research_agent gold-launch-bundle"), calls.index("research_agent.web_server"))
        self.assertNotIn("unit-test-token", completed.stdout + completed.stderr + calls)
        self.assertNotIn("sk-", completed.stdout + completed.stderr + calls)

    def test_execution_timeout_field_is_submitted_from_web_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="timeout_seconds"', index)
        self.assertIn('id="timeout-seconds"', index)

    def test_paper_grade_web_run_actions_use_env_only_secret_payload(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8")

        self.assertIn("data-paper-grade-secret", index)
        self.assertIn('id="llm-api-key-policy"', index)
        self.assertIn("function payloadForRunAction()", app)
        self.assertIn("delete payload.llm_api_key", app)
        self.assertIn("syncPaperGradeSecretPolicy", app)
        self.assertIn("/api/env-llm-preflight", app)
        self.assertIn("envLlmConnectionResult", app)
        self.assertIn("Paper-Grade 使用 Web 服务进程中的 OPENAI_API_KEY", app)
        self.assertIn("JSON.stringify(payloadForRunAction())", app)
        self.assertIn("_reject_paper_grade_payload_secrets", server)
        self.assertIn("paper-grade Web actions require env-only secret handling", server)
        self.assertIn("timeout_seconds", app)

    def test_model_discovery_distinguishes_live_results_from_presets(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        llm = (ROOT / "src" / "research_agent" / "llm.py").read_text(encoding="utf-8")

        self.assertIn('"success": False', llm)
        self.assertIn('"live_api_status": "fail"', llm)
        self.assertIn("res.success === true && res.source === 'live_api'", app)
        self.assertIn("下方仅为推荐预设，使用前必须通过 Ping", app)

    def test_benchmark_schema_summary_is_visible_in_run_list(self) -> None:
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("benchmarkSchemaLabel", app)
        self.assertIn("benchmark_schema", app)
        self.assertIn("Benchmark", app)

    def test_human_brief_fields_are_submitted_from_web_form(self) -> None:
        index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="human_notes"', index)
        self.assertIn('name="human_constraints"', index)
        self.assertIn('name="human_success_criteria"', index)
        self.assertIn('name="human_resource_limits"', index)
        self.assertIn('name="human_risks"', index)
        self.assertIn('data-file="00-human-brief.md"', index)
        self.assertIn("human_notes", app)
        self.assertIn("human_resource_limits", app)


if __name__ == "__main__":
    unittest.main()
