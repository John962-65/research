const stages = [
  ['started', '开始'],
  ['research_plan_completed', '计划画像'],
  ['literature_review_completed', '文献'],
  ['literature_context_completed', '审核包'],
  ['awaiting_review_approval', '待确认'],
  ['review_revision_requested', '退回'],
  ['review_approved', '已确认'],
  ['ideation_completed', 'Ideas'],
  ['exploration_map_completed', '探索'],
  ['experiment_plan_completed', '计划'],
  ['awaiting_execution_approval', '待执行确认'],
  ['execution_approved', '执行确认'],
  ['experiments_completed', '实验'],
  ['analysis_completed', '分析'],
  ['paper_review_completed', '复核'],
  ['revision_plan_completed', '修订'],
  ['paper_revision_completed', '修订稿'],
  ['revision_response_audit_completed', '响应审计'],
  ['final_readiness_completed', '就绪'],
  ['submission_package_completed', '打包'],
  ['iteration_plan_completed', '下一轮'],
  ['llm_trace_audit_completed', 'LLM 审计'],
  ['run_economics_audit_completed', '成本审计'],
  ['llm_runtime_contract_completed', 'LLM 契约'],
  ['agent_observability_audit_completed', '可观测性'],
  ['human_gate_audit_completed', '人工Gate审计'],
  ['repair_queue_completed', '修复队列'],
  ['repair_resolution_audit_completed', '修复闭环'],
  ['agent_stage_contract_completed', '阶段契约'],
  ['scorecard_completed', '分数卡'],
  ['run_integrity_audit_completed', '完整性'],
  ['final_handoff_completed', '交付'],
  ['completed', '完成'],
  ['cancelled', '取消'],
  ['failed', '失败'],
];

const releaseFormFieldByConfigKey = {
  code_repository_url: 'release_code_repository_url',
  code_archive_doi: 'release_code_archive_doi',
  code_license: 'release_code_license',
  code_version: 'release_code_version',
  data_repository_url: 'release_data_repository_url',
  data_archive_doi: 'release_data_archive_doi',
  data_access_statement: 'release_data_access_statement',
  environment_url: 'release_environment_url',
  release_notes: 'release_notes',
};

const releaseFormFieldLabels = {
  release_code_repository_url: '代码仓库 URL',
  release_code_archive_doi: '代码归档 DOI',
  release_code_license: '代码许可证',
  release_code_version: '版本/Commit',
  release_data_repository_url: '数据仓库 URL',
  release_data_archive_doi: '数据归档 DOI',
  release_data_access_statement: '数据访问说明',
  release_environment_url: '环境归档 URL',
  release_notes: '发布备注',
};

const RUN_ACTION_CONFIG_FIELDS = [
  'paper_grade_enabled',
  'execution_mode',
  'llm_provider',
  'llm_base_url',
  'llm_model',
  'llm_max_calls',
  'llm_max_prompt_chars',
  'llm_input_cost_per_million_tokens',
  'llm_output_cost_per_million_tokens',
  'human_notes',
  'human_constraints',
  'human_success_criteria',
  'human_resource_limits',
  'human_risks',
  'literature_provider',
  'literature_sources',
  'extra_search_queries',
  'seed_papers',
  'fulltext_paths',
  'max_papers',
  'max_search_queries',
  'max_ideas',
  'execution_repeats',
  'timeout_seconds',
  'allowed_commands',
  'benchmark_manifests',
  'release_code_repository_url',
  'release_code_archive_doi',
  'release_code_license',
  'release_code_version',
  'release_data_repository_url',
  'release_data_archive_doi',
  'release_data_access_statement',
  'release_environment_url',
  'release_notes',
  'target_venue',
  'paper_style',
];

const RUN_ACTION_REENTERED_FIELDS = [
  'llm_api_key',
  'semantic_scholar_api_key',
  'openalex_api_key',
  'literature_contact_email',
];

const state = {
  runs: [],
  currentRun: null,
  selectedFile: '06-paper.md',
  pollTimer: null,
  pollInFlight: false,
  runsRefreshSequence: 0,
  runLoadSequence: 0,
  runLoadController: null,
  artifactLoadSequence: 0,
  artifactLoadController: null,
  formConfigRunId: null,
  runActionBaseline: null,
  approvingRunId: null,
  revisionRunId: null,
  repairPreviewRunId: null,
  repairPreviewPlan: null,
  literaturePreviewReport: null,
  resumingRunId: null,
  cancellingRunId: null,
  goldLaunchCommands: [],
  goldLaunchChecklist: [],
  currentPage: 1,
  pageSize: 12,
  currentView: 'view-workbench',
  microStepsExpanded: false,
  llmConfigVersion: 0,
  llmPingSequence: 0,
  llmPingController: null,
  modelFetchSequence: 0,
  modelFetchController: null,
};

const els = {
  form: document.querySelector('#run-form'),
  submit: document.querySelector('#submit-run'),
  preflight: document.querySelector('#preflight-run'),
  envLlmPreflight: document.querySelector('#env-llm-preflight'),
  goldEnvLint: document.querySelector('#gold-env-lint'),
  goldEnvLaunchKit: document.querySelector('#gold-env-launch-kit'),
  goldLaunchBundle: document.querySelector('#gold-launch-bundle'),
  goldRunLaunch: document.querySelector('#gold-run-launch'),
  goldRunDoctor: document.querySelector('#gold-run-doctor'),
  goldRunVerify: document.querySelector('#gold-run-verify'),
  literaturePreview: document.querySelector('#literature-preview'),
  paperGradeProbe: document.querySelector('#paper-grade-probe'),
  applyLiteraturePreviewSeeds: document.querySelector('#apply-literature-preview-seeds'),
  benchmarkPreview: document.querySelector('#benchmark-preview'),
  benchmarkTemplate: document.querySelector('#benchmark-template'),
  benchmarkManifestLint: document.querySelector('#benchmark-manifest-lint'),
  benchmarkManifestSave: document.querySelector('#benchmark-manifest-save'),
  benchmarkManifestDraftPath: document.querySelector('#benchmark-manifest-draft-path'),
  benchmarkManifestDraft: document.querySelector('#benchmark-manifest-draft'),
  benchmarkExample: document.querySelector('#apply-benchmark-example'),
  releaseMetadataLint: document.querySelector('#release-metadata-lint'),
  refresh: document.querySelector('#refresh-runs'),
  summary: document.querySelector('#summary-runs'),
  platformAudit: document.querySelector('#platform-audit'),
  perfectReadiness: document.querySelector('#perfect-readiness'),
  openSourceBackfillPreview: document.querySelector('#open-source-backfill-preview'),
  openSourceBackfillRun: document.querySelector('#open-source-backfill-run'),
  llmBackfillPreview: document.querySelector('#llm-backfill-preview'),
  llmBackfillRun: document.querySelector('#llm-backfill-run'),
  repairBacklog: document.querySelector('#repair-backlog'),
  repairBackfillPreview: document.querySelector('#repair-backfill-preview'),
  repairBackfillRun: document.querySelector('#repair-backfill-run'),
  applyMemoryDefaults: document.querySelector('#apply-memory-defaults'),
  applyGoldDefaults: document.querySelector('#apply-gold-defaults'),
  goldDefaultsSmoke: document.querySelector('#gold-defaults-smoke'),
  libraryQuery: document.querySelector('#library-query'),
  librarySearch: document.querySelector('#library-search'),
  runList: document.querySelector('#run-list'),
  title: document.querySelector('#current-title'),
  status: document.querySelector('#status-pill'),
  approve: document.querySelector('#approve-run'),
  revision: document.querySelector('#revision-run'),
  repairResumePreview: document.querySelector('#repair-resume-preview'),
  applyRepairResume: document.querySelector('#apply-repair-resume'),
  resume: document.querySelector('#resume-run'),
  applyLiteratureFeedback: document.querySelector('#apply-literature-feedback'),
  cancel: document.querySelector('#cancel-run'),
  stageTrack: document.querySelector('#stage-track'),
  artifactTitle: document.querySelector('#artifact-title'),
  artifactContent: document.querySelector('#artifact-content'),
  artifactRendered: document.querySelector('#artifact-rendered'),
  btnViewAcademic: document.querySelector('#btn-view-academic'),
  btnViewRaw: document.querySelector('#btn-view-raw'),
  catFilterBtns: [...document.querySelectorAll('.cat-filter-btn')],
  goldLaunchCommandPanel: document.querySelector('#gold-launch-command-panel'),
  goldLaunchChecklist: document.querySelector('#gold-launch-checklist'),
  goldLaunchCommandText: document.querySelector('#gold-launch-command-text'),
  copyGoldLaunchCommands: document.querySelector('#copy-gold-launch-commands'),
  downloadLink: document.querySelector('#download-link'),
  tabs: [...document.querySelectorAll('.artifact-tab')],
};

function stageIndex(stage) {
  const index = stages.findIndex(([key]) => key === stage);
  return index === -1 ? 0 : index;
}

const milestones = [
  { id: 'plan', num: '01', title: '规划画像', stages: ['started', 'research_plan_completed'] },
  { id: 'lit', num: '02', title: '文献检索', stages: ['literature_review_completed', 'literature_context_completed', 'awaiting_review_approval', 'review_revision_requested', 'review_approved'] },
  { id: 'idea', num: '03', title: 'Idea探索', stages: ['ideation_completed', 'exploration_map_completed', 'experiment_plan_completed', 'awaiting_execution_approval', 'execution_approved'] },
  { id: 'exp', num: '04', title: '实验统计', stages: ['experiments_completed', 'analysis_completed'] },
  { id: 'paper', num: '05', title: '论文审稿', stages: ['paper_review_completed', 'revision_plan_completed', 'paper_revision_completed', 'revision_response_audit_completed'] },
  { id: 'audit', num: '06', title: '溯源归档', stages: ['final_readiness_completed', 'submission_package_completed', 'iteration_plan_completed', 'llm_trace_audit_completed', 'run_economics_audit_completed', 'llm_runtime_contract_completed', 'agent_observability_audit_completed', 'human_gate_audit_completed', 'repair_queue_completed', 'repair_resolution_audit_completed', 'agent_stage_contract_completed', 'scorecard_completed', 'run_integrity_audit_completed', 'final_handoff_completed', 'completed'] },
];

function renderStages(stage, workflow) {
  const currentIdx = stageIndex(stage);
  const currentStageInfo = stages[currentIdx] || ['started', '开始'];
  const percent = stage === 'completed' ? 100 : Math.round((currentIdx / Math.max(1, stages.length - 1)) * 100);

  let activeMilestoneIdx = milestones.findIndex(m => m.stages.includes(stage));
  if (activeMilestoneIdx === -1) {
    if (stage === 'completed') activeMilestoneIdx = milestones.length - 1;
    else activeMilestoneIdx = 0;
  }

  const milestonesHtml = milestones.map((m, idx) => {
    const isDone = idx < activeMilestoneIdx || stage === 'completed';
    const isCurrent = idx === activeMilestoneIdx && stage !== 'completed';
    const cls = isDone ? 'done' : isCurrent ? 'current' : 'pending';
    return `
      <div class="milestone-node ${cls}">
        <div class="milestone-marker">${isDone ? '✓' : m.num}</div>
        <div class="milestone-label">${m.title}</div>
      </div>
    `;
  }).join('<div class="milestone-line"></div>');

  const microStepsHtml = stages.map(([key, name], index) => {
    const cls = index < currentIdx || stage === 'completed' ? 'done' : index === currentIdx ? 'current' : '';
    return `<div class="stage-step ${cls}"><span class="stage-index">${String(index + 1).padStart(2, '0')}</span><span class="stage-name">${name}</span></div>`;
  }).join('');

  const isExpanded = Boolean(state.microStepsExpanded);
  const workflowHtml = renderWorkflowPanel(workflow);

  els.stageTrack.innerHTML = `
    ${workflowHtml}
    <div class="compact-stepper-wrapper">
      <div class="milestones-bar">
        ${milestonesHtml}
      </div>
      <div class="stepper-sub-bar">
        <div class="stepper-status-text">
          <span class="stepper-badge">步骤 ${currentIdx + 1}/${stages.length}</span>
          <span class="stepper-curr-name">${currentStageInfo[1]} (${currentStageInfo[0]})</span>
        </div>
        <div class="stepper-progress-box">
          <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${percent}%"></div></div>
          <span class="progress-percent">${percent}%</span>
        </div>
        <button id="btn-toggle-microsteps" class="mini-button micro-toggle-btn ${isExpanded ? 'active' : ''}" type="button" aria-controls="micro-steps-drawer" aria-expanded="${isExpanded ? 'true' : 'false'}">
          <span>${isExpanded ? '收起微步骤' : '全部微步骤 (' + stages.length + ')'}</span> ${isExpanded ? '▴' : '▾'}
        </button>
      </div>
      <div id="micro-steps-drawer" class="micro-steps-drawer" ${isExpanded ? '' : 'hidden'}>
        <div class="micro-steps-grid">${microStepsHtml}</div>
      </div>
    </div>
  `;

  const toggleBtn = document.querySelector('#btn-toggle-microsteps');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      state.microStepsExpanded = !state.microStepsExpanded;
      renderStages(state.currentRun?.stage || 'started', state.currentRun?.workflow);
    });
  }
}

const WORKFLOW_STATUS_LABELS = { running: '运行中', waiting: '等待人工', completed: '已完成', pending: '未开始', failed: '失败', cancelled: '已取消' };

function renderWorkflowPanel(workflow) {
  if (!workflow || !Array.isArray(workflow.nodes) || !workflow.nodes.length) return '';
  const activityStatus = WORKFLOW_STATUS_LABELS[workflow.activity_status] || workflow.activity_status || '';
  const nodesHtml = workflow.nodes.map(node => {
    const status = node.status || 'pending';
    const label = WORKFLOW_STATUS_LABELS[status] || status;
    const title = `${node.title} · ${node.role} · ${label}\n${node.task || ''}`;
    return `
      <div class="workflow-node ${status}" title="${escapeHtml(title)}">
        <span class="workflow-node-dot"></span>
        <span class="workflow-node-title">${escapeHtml(node.title)}</span>
      </div>
    `;
  }).join('<span class="workflow-node-arrow">→</span>');

  const agentEvents = (workflow.events || []).filter(event => event.kind === 'agent').slice(-8).reverse();
  const activityHtml = agentEvents.length ? `
    <div class="workflow-activity">
      <div class="workflow-activity-header">智能体活动</div>
      <ul class="workflow-activity-list">
        ${agentEvents.map(event => {
          const statusLabel = WORKFLOW_STATUS_LABELS[event.status] || event.status || '';
          return `<li class="workflow-activity-item status-${escapeHtml(event.status || 'unknown')}">
            <span class="workflow-activity-time">${escapeHtml((event.at || '').slice(11, 19))}</span>
            <span class="workflow-activity-agent">${escapeHtml(event.agent_id || '-')}</span>
            <span class="workflow-activity-task">${escapeHtml(event.task || '')}</span>
            <span class="workflow-activity-model">${escapeHtml(event.model || '')}</span>
            <span class="workflow-activity-status">${escapeHtml(statusLabel)}</span>
          </li>`;
        }).join('')}
      </ul>
    </div>
  ` : '';

  return `
    <div class="workflow-panel">
      <div class="workflow-panel-header">
        <span class="workflow-progress-badge">${escapeHtml(String(workflow.completed_nodes ?? 0))}/${escapeHtml(String(workflow.total_nodes ?? workflow.nodes.length))} 节点</span>
        <span class="workflow-current">${escapeHtml(workflow.current_node_title || '')}</span>
        <span class="workflow-activity-status-badge">${escapeHtml(activityStatus)}</span>
      </div>
      <div class="workflow-nodes-bar">${nodesHtml}</div>
      ${activityHtml}
    </div>
  `;
}

function statusClass(status) {
  return ['running', 'waiting', 'revision_requested', 'cancelling', 'cancelled', 'completed', 'failed', 'unknown'].includes(status) ? status : 'idle';
}

function canApprove(run) {
  if (!run || !['awaiting_review_approval', 'review_revision_requested', 'awaiting_execution_approval'].includes(run.stage)) return false;
  if (['cancelling', 'cancelled'].includes(run.status)) return false;
  const approval = run.stage === 'awaiting_execution_approval' ? run.execution_approval : run.approval;
  if (run.worker_active) return run.status === 'waiting' && !approval?.approved;
  return ['waiting', 'unknown', 'revision_requested'].includes(run.status);
}

function approvalNotesRequired(run) {
  const approval = run?.stage === 'awaiting_execution_approval' ? run?.execution_approval || {} : run?.approval || {};
  const policy = approval.approval_policy || {};
  if (policy.notes_required === true) return true;
  const status = String(approval.gate_status || policy.gate_status || '').trim();
  return Boolean(status) && !['pass', 'unknown'].includes(status);
}

function canRequestRevision(run) {
  if (!run || run.stage !== 'awaiting_review_approval') return false;
  if (run.approval?.approved) return false;
  return ['waiting', 'running'].includes(run.status);
}

function canCancel(run) {
  if (!run) return false;
  if (['completed', 'failed', 'cancelled'].includes(run.status)) return false;
  if (['completed', 'failed', 'cancelled'].includes(run.stage)) return false;
  return ['running', 'waiting', 'unknown', 'cancelling'].includes(run.status);
}

function canResume(run) {
  if (!run || run.worker_active) return false;
  if (canRepairResume(run)) return true;
  if (['completed', 'cancelled', 'cancelling'].includes(run.status)) return false;
  if (['completed', 'cancelled', 'awaiting_review_approval', 'awaiting_execution_approval'].includes(run.stage)) return false;
  return ['failed', 'unknown'].includes(run.status);
}

function canRepairResume(run) {
  if (!run || run.worker_active) return false;
  if (['cancelled', 'cancelling'].includes(run.status) || run.stage === 'cancelled') return false;
  if (['blocked_repair_required', 'needs_repair'].includes(run.repair_queue?.status)) return true;
  return run.repair_resume_plan?.can_resume === true && run.repair_resume_plan?.status === 'ready_to_resume_repair';
}

function canApplyLiteratureFeedback(run) {
  const feedback = run?.literature_search_feedback;
  const rescue = run?.literature_rescue_plan;
  const execution = run?.literature_rescue_execution;
  const seed = run?.seed_intake;
  if (!feedback && !rescue && !execution && !seed) return false;
  const config = feedback?.next_run_config || {};
  const hasConfig = Boolean(config.literature_provider || Number(config.max_papers || 0) || Number(config.max_search_queries || 0) || (Array.isArray(config.sources) && config.sources.length));
  const hasQueries = Array.isArray(feedback?.top_queries) && feedback.top_queries.length > 0;
  const hasRescueQueries = (Array.isArray(rescue?.role_queries) && rescue.role_queries.length > 0) || (Array.isArray(rescue?.top_queries) && rescue.top_queries.length > 0);
  const hasUnresolvedQueries = Array.isArray(execution?.unresolved_queries) && execution.unresolved_queries.length > 0;
  const hasSeedRoleQueries = Array.isArray(seed?.role_repair_queries) && seed.role_repair_queries.length > 0;
  const hasSuggestedSeedEntries = Array.isArray(seed?.suggested_seed_entries) && seed.suggested_seed_entries.length > 0;
  return hasConfig || hasQueries || hasRescueQueries || hasUnresolvedQueries || hasSeedRoleQueries || hasSuggestedSeedEntries;
}

function canApplyLiteraturePreviewSeeds() {
  const report = state.literaturePreviewReport;
  if (!report || !Array.isArray(report.recommended_seed_entries) || !report.recommended_seed_entries.length) return false;
  const currentTopic = String(els.form.elements.namedItem('topic')?.value || '').trim();
  return Boolean(currentTopic && String(report.topic || '').trim() === currentTopic);
}

function canApplyRepairResumePreview(run) {
  if (!run || !state.repairPreviewPlan) return false;
  if (state.repairPreviewPlan.run_id && state.repairPreviewPlan.run_id !== run.id) return false;
  const plan = state.repairPreviewPlan.plan || state.repairPreviewPlan;
  if (!plan || plan.can_resume !== true) return false;
  const literature = plan.recommended_config || {};
  const execution = plan.recommended_execution_config || {};
  const paperGrade = plan.recommended_paper_grade_config || {};
  const release = plan.recommended_release_config || {};
  return Boolean(
    literature.literature_provider
    || Number(literature.max_papers || 0)
    || Number(literature.max_search_queries || 0)
    || (Array.isArray(literature.sources) && literature.sources.length)
    || execution.execution_mode
    || Number(execution.execution_repeats || 0)
    || Number(execution.timeout_seconds || 0)
    || (Array.isArray(execution.allowed_commands) && execution.allowed_commands.length)
    || (Array.isArray(execution.benchmark_manifest_paths) && execution.benchmark_manifest_paths.length)
    || paperGrade.enabled === true
    || releaseConfigValues(release).length
  );
}

function releaseConfigValues(releaseConfig) {
  const fields = releaseConfig?.config_fields || {};
  if (!fields || typeof fields !== 'object' || Array.isArray(fields)) return [];
  return Object.entries(fields)
    .map(([key, value]) => [key, String(value || '').trim()])
    .filter(([key, value]) => releaseFormFieldByConfigKey[key] && value);
}

function configListValue(value, separator) {
  if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean).join(separator);
  return String(value || '').trim();
}

function publicRunConfigPayload(run) {
  const config = run?.config;
  if (!config || typeof config !== 'object') return null;
  const llm = config.llm || {};
  const literature = config.literature || {};
  const ideation = config.ideation || {};
  const execution = config.execution || {};
  const paper = config.paper || {};
  const paperGrade = config.paper_grade || {};
  const release = config.release || {};
  const human = config.human || {};
  return {
    paper_grade_enabled: paperGrade.enabled === true,
    execution_mode: String(execution.mode || 'simulated'),
    llm_provider: String(llm.provider || 'openai-compatible'),
    llm_base_url: String(llm.base_url || '').trim(),
    llm_model: String(llm.model || '').trim(),
    llm_max_calls: Number(llm.max_calls || 0),
    llm_max_prompt_chars: Number(llm.max_prompt_chars || 0),
    llm_input_cost_per_million_tokens: Number(llm.input_cost_per_million_tokens || 0),
    llm_output_cost_per_million_tokens: Number(llm.output_cost_per_million_tokens || 0),
    human_notes: configListValue(human.notes, '\n'),
    human_constraints: configListValue(human.constraints, '\n'),
    human_success_criteria: configListValue(human.success_criteria, '\n'),
    human_resource_limits: configListValue(human.resource_limits, '\n'),
    human_risks: configListValue(human.risks, '\n'),
    literature_provider: String(literature.provider || 'offline'),
    literature_sources: configListValue(literature.sources, ', '),
    extra_search_queries: configListValue(literature.extra_search_queries, '\n'),
    seed_papers: configListValue(literature.seed_papers, '\n'),
    fulltext_paths: configListValue(literature.fulltext_paths, '\n'),
    max_papers: Number(literature.max_papers || 8),
    max_search_queries: Number(literature.max_search_queries || 4),
    max_ideas: Number(ideation.max_ideas || 5),
    execution_repeats: Number(execution.repeats || 5),
    timeout_seconds: Number(execution.timeout_seconds || 300),
    allowed_commands: configListValue(execution.allowed_commands, ', '),
    benchmark_manifests: configListValue(execution.benchmark_manifest_paths, '\n'),
    release_code_repository_url: String(release.code_repository_url || '').trim(),
    release_code_archive_doi: String(release.code_archive_doi || '').trim(),
    release_code_license: String(release.code_license || '').trim(),
    release_code_version: String(release.code_version || '').trim(),
    release_data_repository_url: String(release.data_repository_url || '').trim(),
    release_data_archive_doi: String(release.data_archive_doi || '').trim(),
    release_data_access_statement: String(release.data_access_statement || '').trim(),
    release_environment_url: String(release.environment_url || '').trim(),
    release_notes: String(release.release_notes || '').trim(),
    target_venue: String(paper.target_venue || 'workshop'),
    paper_style: String(paper.style || 'concise'),
  };
}

function clearRunSecretFields() {
  for (const name of RUN_ACTION_REENTERED_FIELDS) setFieldValue(name, '');
}

function applyRunConfigToForm(run) {
  clearRunSecretFields();
  setFieldValue('review_notes', '');
  setFieldValue('benchmark_pack_run_dir', '');
  setFieldValue('fulltext_grounding_run_dir', '');
  if (!run) {
    state.formConfigRunId = null;
    state.runActionBaseline = null;
    return;
  }

  const payload = publicRunConfigPayload(run);
  if (!payload) return;
  setFieldValue('topic', run.topic || '');
  for (const [name, value] of Object.entries(payload)) {
    if (name === 'paper_grade_enabled') continue;
    setFieldValue(name, value);
  }
  const paperGradeField = els.form.elements.namedItem('paper_grade_enabled');
  if (paperGradeField && 'checked' in paperGradeField) paperGradeField.checked = payload.paper_grade_enabled;
  state.formConfigRunId = run.id;
  state.runActionBaseline = {...payload};
  syncPaperGradeSecretPolicy();
  invalidateLlmConnectionStatus({clearModels: true});
}

function setCurrentRun(run) {
  const runChanged = state.currentRun?.id !== run?.id;
  if (!run || runChanged) {
    state.repairPreviewPlan = null;
  }
  state.currentRun = run;
  if (runChanged || (run?.config && state.formConfigRunId !== run.id)) {
    applyRunConfigToForm(run);
  }
  const title = run ? run.topic : '尚未选择';
  if (els.title.textContent !== title) els.title.textContent = title;
  const status = run ? run.status : 'idle';
  if (els.status.textContent !== status) els.status.textContent = status;
  els.status.className = `status-pill ${statusClass(status)}`;
  renderStages(run ? run.stage : 'started', run?.workflow);
  updateActionButtons();
  updateTabs();
}

function updateActionButtons() {
  const allowed = canApprove(state.currentRun);
  const approving = Boolean(state.currentRun && state.approvingRunId === state.currentRun.id);
  els.approve.hidden = !allowed && !approving;
  els.approve.disabled = !allowed || approving;
  const needsResume = Boolean(state.currentRun && !state.currentRun.worker_active);
  const executionApproval = state.currentRun?.stage === 'awaiting_execution_approval';
  els.approve.textContent = approving ? '批准中...' : executionApproval ? (needsResume ? '批准并恢复执行' : '批准执行') : needsResume ? '批准并恢复' : '批准继续';

  const revisionAllowed = canRequestRevision(state.currentRun);
  const revising = Boolean(state.currentRun && state.revisionRunId === state.currentRun.id);
  els.revision.hidden = !revisionAllowed && !revising;
  els.revision.disabled = !revisionAllowed || revising;
  els.revision.textContent = revising ? '退回中...' : '退回';

  const resumeAllowed = canResume(state.currentRun);
  const resuming = Boolean(state.currentRun && state.resumingRunId === state.currentRun.id);
  els.resume.hidden = !resumeAllowed && !resuming;
  els.resume.disabled = !resumeAllowed || resuming;
  els.resume.textContent = resuming ? '恢复中...' : canRepairResume(state.currentRun) ? '修复恢复' : '恢复';

  const repairPreviewAllowed = canRepairResume(state.currentRun);
  const repairPreviewing = Boolean(state.currentRun && state.repairPreviewRunId === state.currentRun.id);
  els.repairResumePreview.hidden = !repairPreviewAllowed && !repairPreviewing;
  els.repairResumePreview.disabled = !repairPreviewAllowed || repairPreviewing || resuming;
  els.repairResumePreview.textContent = repairPreviewing ? '预览中...' : '预览修复';

  const applyRepairAllowed = canApplyRepairResumePreview(state.currentRun);
  els.applyRepairResume.hidden = !applyRepairAllowed;
  els.applyRepairResume.disabled = !applyRepairAllowed || resuming;

  const feedbackAllowed = canApplyLiteratureFeedback(state.currentRun);
  els.applyLiteratureFeedback.hidden = !feedbackAllowed;
  els.applyLiteratureFeedback.disabled = !feedbackAllowed;

  const previewSeedsAllowed = canApplyLiteraturePreviewSeeds();
  els.applyLiteraturePreviewSeeds.hidden = !previewSeedsAllowed;
  els.applyLiteraturePreviewSeeds.disabled = !previewSeedsAllowed;

  const cancelAllowed = canCancel(state.currentRun);
  const cancelling = Boolean(state.currentRun && (state.cancellingRunId === state.currentRun.id || state.currentRun.status === 'cancelling'));
  els.cancel.hidden = !cancelAllowed && !cancelling;
  els.cancel.disabled = !cancelAllowed || cancelling;
  els.cancel.textContent = cancelling ? '取消中...' : '停止';

  els.goldRunVerify.disabled = !state.currentRun?.id;
}

function updateTabs() {
  const artifacts = new Set(state.currentRun?.artifacts || []);
  els.tabs.forEach((tab) => {
    const file = tab.dataset.file;
    tab.disabled = Boolean(state.currentRun) && !artifacts.has(file);
    tab.classList.toggle('active', file === state.selectedFile);
    tab.setAttribute('aria-current', file === state.selectedFile ? 'page' : 'false');
  });
}

function switchView(viewId) {
  state.currentView = viewId;
  document.querySelectorAll('.view-section').forEach((sec) => {
    const active = sec.id === viewId;
    sec.classList.toggle('active-view', active);
    sec.hidden = !active;
  });
  document.querySelectorAll('.nav-tab-btn').forEach((btn) => {
    const active = btn.dataset.view === viewId;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
    btn.tabIndex = active ? 0 : -1;
  });
}

function updateHeaderStatus() {
  const headerTopic = document.querySelector('#header-current-topic');
  if (headerTopic) {
    headerTopic.textContent = state.currentRun ? state.currentRun.topic : '尚未选择课题';
  }
  const runsBadge = document.querySelector('#runs-count-badge');
  if (runsBadge) {
    runsBadge.textContent = state.runs.length;
  }
}

function renderRunList() {
  updateHeaderStatus();
  if (!state.runs.length) {
    els.runList.innerHTML = '<div class="run-archive-card"><div class="run-card-title">暂无科研 Run</div><div class="run-card-tags"><span>提交课题后显示</span></div></div>';
    const info = document.querySelector('#pagination-info');
    if (info) info.textContent = '共 0 条记录';
    return;
  }

  const total = state.runs.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  if (state.currentPage < 1) state.currentPage = 1;

  const start = (state.currentPage - 1) * state.pageSize;
  const end = Math.min(start + state.pageSize, total);
  const pagedRuns = state.runs.slice(start, end);

  els.runList.innerHTML = pagedRuns.map((run) => {
    const active = state.currentRun?.id === run.id ? 'active' : '';
    const finalGate = finalGateLabel(run);
    const availability = availabilityLabel(run);
    const submission = submissionLabel(run);
    const submissionPackage = packageLabel(run);
    const iteration = iterationLabel(run);
    const repair = repairQueueLabel(run);
    const repairResume = repairResumeLabel(run);
    const goldDoctor = goldRunDoctorLabel(run);
    const goldVerify = goldRunVerifyLabel(run);
    const repairResolution = repairResolutionLabel(run);
    const manager = experimentManagerLabel(run);
    const ideaGate = ideaExperimentGateLabel(run);
    const benchmarkSchema = benchmarkSchemaLabel(run);
    const literatureRepair = literatureRepairLabel(run);
    const retrievalGate = literatureRetrievalGateLabel(run);
    const evidenceContract = literatureEvidenceContractLabel(run);
    const literatureGate = literatureQualityGateLabel(run);
    const rescuePlan = literatureRescuePlanLabel(run);
    const rescueExecution = literatureRescueExecutionLabel(run);
    const seedIntake = seedIntakeLabel(run);
    const integrity = runIntegrityLabel(run);
    const handoff = finalHandoffLabel(run);
    const trajectory = agentTrajectoryLabel(run);
    const observability = agentObservabilityLabel(run);
    const humanGateAudit = humanGateAuditLabel(run);
    const llmRuntime = llmRuntimeContractLabel(run);
    const llmObservability = llmObservabilityLabel(run);
    const openSource = openSourceComplianceLabel(run);

    return `<div class="run-archive-card run-item ${active}" data-id="${escapeHtml(run.id)}">
      <div>
        <div class="run-card-title run-item-title">${escapeHtml(run.topic)}</div>
        <div class="run-card-tags run-item-meta">
          <span class="status-badge ${statusClass(run.status)}">${escapeHtml(run.status)}</span>
          <span>${escapeHtml(run.stage)}</span>
          ${retrievalGate ? `<span>${escapeHtml(retrievalGate)}</span>` : ''}
          ${evidenceContract ? `<span>${escapeHtml(evidenceContract)}</span>` : ''}
          ${literatureGate ? `<span>${escapeHtml(literatureGate)}</span>` : ''}
          ${literatureRepair ? `<span>${escapeHtml(literatureRepair)}</span>` : ''}
          ${rescuePlan ? `<span>${escapeHtml(rescuePlan)}</span>` : ''}
          ${rescueExecution ? `<span>${escapeHtml(rescueExecution)}</span>` : ''}
          ${seedIntake ? `<span>${escapeHtml(seedIntake)}</span>` : ''}
          ${manager ? `<span>${escapeHtml(manager)}</span>` : ''}
          ${ideaGate ? `<span>${escapeHtml(ideaGate)}</span>` : ''}
          ${benchmarkSchema ? `<span>${escapeHtml(benchmarkSchema)}</span>` : ''}
          ${goldDoctor ? `<span>${escapeHtml(goldDoctor)}</span>` : ''}
          ${goldVerify ? `<span>${escapeHtml(goldVerify)}</span>` : ''}
          ${finalGate ? `<span>${escapeHtml(finalGate)}</span>` : ''}
          ${availability ? `<span>${escapeHtml(availability)}</span>` : ''}
          ${submission ? `<span>${escapeHtml(submission)}</span>` : ''}
          ${submissionPackage ? `<span>${escapeHtml(submissionPackage)}</span>` : ''}
          ${iteration ? `<span>${escapeHtml(iteration)}</span>` : ''}
          ${trajectory ? `<span>${escapeHtml(trajectory)}</span>` : ''}
          ${humanGateAudit ? `<span>${escapeHtml(humanGateAudit)}</span>` : ''}
          ${llmRuntime ? `<span>${escapeHtml(llmRuntime)}</span>` : ''}
          ${llmObservability ? `<span>${escapeHtml(llmObservability)}</span>` : ''}
          ${openSource ? `<span>${escapeHtml(openSource)}</span>` : ''}
          ${observability ? `<span>${escapeHtml(observability)}</span>` : ''}
          ${integrity ? `<span>${escapeHtml(integrity)}</span>` : ''}
          ${handoff ? `<span>${escapeHtml(handoff)}</span>` : ''}
          ${repairResolution ? `<span>${escapeHtml(repairResolution)}</span>` : ''}
          ${repairResume ? `<span>${escapeHtml(repairResume)}</span>` : ''}
          ${repair ? `<span>${escapeHtml(repair)}</span>` : ''}
        </div>
      </div>
      <div class="run-card-footer">
        <span>ID: ${escapeHtml(run.id.slice(-18))}</span>
        <button class="mini-button" type="button" data-id="${escapeHtml(run.id)}">在工作台打开 ➔</button>
      </div>
    </div>`;
  }).join('');

  renderPagination(total, totalPages, start, end);
}

function renderPagination(total, totalPages, start, end) {
  const info = document.querySelector('#pagination-info');
  if (info) {
    info.textContent = `显示第 ${start + 1} - ${end} 项，共 ${total} 个科研 Runs`;
  }
  const pagePrev = document.querySelector('#page-prev');
  const pageNext = document.querySelector('#page-next');
  if (pagePrev) pagePrev.disabled = state.currentPage <= 1;
  if (pageNext) pageNext.disabled = state.currentPage >= totalPages;

  const pageNumbers = document.querySelector('#page-numbers');
  if (pageNumbers) {
    let pagesHtml = '';
    const maxButtons = 5;
    let startPage = Math.max(1, state.currentPage - 2);
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    if (endPage - startPage < maxButtons - 1) {
      startPage = Math.max(1, endPage - maxButtons + 1);
    }
    for (let p = startPage; p <= endPage; p++) {
      pagesHtml += `<button class="page-btn ${p === state.currentPage ? 'active' : ''}" type="button" data-page="${p}">${p}</button>`;
    }
    pageNumbers.innerHTML = pagesHtml;
  }
}

function finalGateLabel(run) {
  const readiness = run?.final_readiness;
  if (!readiness?.status) return '';
  const score = Number.isFinite(Number(readiness.score_after)) ? ` ${Number(readiness.score_after).toFixed(1)}` : '';
  const blocks = Number(readiness.deferred_tasks || 0) + Number(readiness.blocking_issues || 0) + Number(readiness.unsupported_after || 0);
  return blocks ? `${readiness.status}${score} / 阻断${blocks}` : `${readiness.status}${score}`;
}

function availabilityLabel(run) {
  const availability = run?.availability;
  if (!availability?.status) return '';
  const blocks = Number(availability.blocking_issues || 0) + Number(availability.manual_tasks || 0);
  return blocks ? `代码/数据 ${availability.status} / 待办${blocks}` : `代码/数据 ${availability.status}`;
}

function submissionLabel(run) {
  const readiness = run?.final_readiness;
  if (!readiness?.submission_status) return '';
  const tasks = Number(readiness.submission_blocking_issues || 0) + Number(readiness.submission_manual_tasks || 0);
  return tasks ? `投稿 ${readiness.submission_status} / 待办${tasks}` : `投稿 ${readiness.submission_status}`;
}

function packageLabel(run) {
  const pack = run?.submission_package;
  if (!pack?.status) return '';
  const tasks = Number(pack.blocking_issues || 0) + Number(pack.manual_tasks || 0);
  return tasks ? `投稿包 ${pack.status} / 待办${tasks}` : `投稿包 ${pack.status}`;
}

function iterationLabel(run) {
  const plan = run?.iteration_plan;
  if (!plan?.status) return '';
  const items = Number(plan.items || 0);
  return items ? `下一轮 ${plan.status} / ${items}项` : `下一轮 ${plan.status}`;
}

function experimentManagerLabel(run) {
  const manager = run?.experiment_manager;
  if (!manager?.status) return '';
  const policy = manager.execution_policy ? `/${manager.execution_policy}` : '';
  const next = Number(manager.next_candidates || 0);
  const blocked = Number(manager.queue_blocked || 0);
  const human = Number(manager.queue_human_review || 0);
  const ready = Number(manager.queue_ready_backlog || 0);
  const queue = [
    blocked ? `B${blocked}` : '',
    human ? `H${human}` : '',
    ready ? `R${ready}` : '',
  ].filter(Boolean).join(' ');
  const suffix = [next ? `N${next}` : '', queue ? `Q ${queue}` : ''].filter(Boolean).join(' / ');
  return suffix ? `实验管理 ${manager.status}${policy} ${suffix}` : `实验管理 ${manager.status}${policy}`;
}

function benchmarkSchemaLabel(run) {
  const schema = run?.benchmark_schema;
  if (!schema?.status) return '';
  const blocking = Number(schema.blocking_issues || 0);
  const manual = Number(schema.manual_tasks || 0);
  const warnings = Number(schema.warnings || 0);
  const issues = [blocking ? `B${blocking}` : '', manual ? `M${manual}` : '', warnings ? `W${warnings}` : ''].filter(Boolean).join(' ');
  return issues ? `Benchmark ${schema.status} / ${issues}` : `Benchmark ${schema.status}`;
}

function ideaExperimentGateLabel(run) {
  const gate = run?.idea_experiment_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const blocking = Number(gate.blocking_issues || 0);
  const manual = Number(gate.manual_tasks || 0);
  const warnings = Number(gate.warnings || 0);
  const safety = Number(gate.safety_blocking_issues || 0);
  const benchmark = Number(gate.benchmark_blocking_issues || 0);
  const parts = [blocking ? `B${blocking}` : '', manual ? `M${manual}` : '', warnings ? `W${warnings}` : '', safety ? `安全${safety}` : '', benchmark ? `Bench${benchmark}` : ''].filter(Boolean).join(' ');
  return parts ? `Idea/实验门禁 ${gate.status} / ${parts}` : `Idea/实验门禁 ${gate.status}`;
}

function ideaExperimentGateDetails(run) {
  const gate = run?.idea_experiment_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const lines = ['Idea/实验门禁摘要：'];
  if (gate.selected_idea_title) lines.push(`- 选中 idea：${gate.selected_idea_title}`);
  if (gate.execution_mode) lines.push(`- 执行模式：${gate.execution_mode}`);
  const statuses = [
    gate.novelty_status ? `novelty=${gate.novelty_status}` : '',
    gate.idea_audit_status ? `idea=${gate.idea_audit_status}` : '',
    gate.experiment_manager_status ? `manager=${gate.experiment_manager_status}` : '',
    gate.experiment_audit_status ? `experiment=${gate.experiment_audit_status}` : '',
    gate.contract_status ? `contract=${gate.contract_status}` : '',
    gate.execution_safety_status ? `safety=${gate.execution_safety_status}` : '',
    gate.benchmark_readiness_status ? `benchmark=${gate.benchmark_readiness_status}` : '',
    gate.benchmark_adapter_status ? `adapter=${gate.benchmark_adapter_status}` : '',
  ].filter(Boolean).join('；');
  if (statuses) lines.push(`- 子门禁：${statuses}`);
  const blocking = Number(gate.blocking_issues || 0);
  const manual = Number(gate.manual_tasks || 0);
  const warnings = Number(gate.warnings || 0);
  if (blocking || manual || warnings) lines.push(`- 问题计数：阻断 ${blocking}，人工待办 ${manual}，警告 ${warnings}`);
  if (Number(gate.safety_blocking_issues || 0)) lines.push(`- 执行安全阻断：${gate.safety_blocking_issues}`);
  if (Number(gate.benchmark_blocking_issues || 0)) lines.push(`- Benchmark 阻断：${gate.benchmark_blocking_issues}`);
  lines.push(`- 建议：${gate.approval_hint || '批准执行前应填写审核意见，确认风险已修复或接受。'}`);
  return lines.join('\n');
}

function literatureRetrievalGateLabel(run) {
  const gate = run?.literature_retrieval_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const success = Number(gate.sources_with_success || 0);
  const configured = Number(gate.configured_sources || 0);
  const queries = Number(gate.selected_queries || 0);
  const raw = Number(gate.raw_candidates || 0);
  const rateLimited = Number(gate.rate_limited_sources || 0);
  const failed = Number(gate.failed_sources || 0);
  const zero = Number(gate.queries_with_zero_source_results || 0);
  const parts = [configured ? `${success}/${configured}源` : '', queries ? `Q${queries}` : '', raw ? `N${raw}` : '', rateLimited ? `429:${rateLimited}` : '', failed ? `Fail${failed}` : '', zero ? `Zero${zero}` : ''].filter(Boolean).join(' ');
  return parts ? `检索门禁 ${gate.status} / ${parts}` : `检索门禁 ${gate.status}`;
}

function literatureRetrievalGateDetails(run) {
  const gate = run?.literature_retrieval_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const lines = ['检索门禁摘要：'];
  const configured = Number(gate.configured_sources || 0);
  const success = Number(gate.sources_with_success || 0);
  if (configured || success) lines.push(`- 来源成功/配置：${success}/${configured}`);
  const selected = Number(gate.selected_queries || 0);
  const attempts = Number(gate.query_attempts || 0);
  const successes = Number(gate.query_successes || 0);
  if (selected || attempts) lines.push(`- Query：selected=${selected}，attempts=${attempts}，successes=${successes}`);
  if (Number(gate.raw_candidates || 0)) lines.push(`- 原始候选：${gate.raw_candidates}`);
  if (Number(gate.queries_with_zero_source_results || 0)) lines.push(`- 零返回 query：${gate.queries_with_zero_source_results}`);
  if (Array.isArray(gate.rate_limited_source_names) && gate.rate_limited_source_names.length) lines.push(`- 限流来源：${gate.rate_limited_source_names.join(', ')}`);
  if (Array.isArray(gate.failed_source_names) && gate.failed_source_names.length) lines.push(`- 失败来源：${gate.failed_source_names.join(', ')}`);
  if (Array.isArray(gate.missing_required_intents) && gate.missing_required_intents.length) lines.push(`- 缺失检索意图：${gate.missing_required_intents.join(', ')}`);
  const statuses = [
    gate.query_execution_status ? `query=${gate.query_execution_status}` : '',
    gate.rerank_status ? `rerank=${gate.rerank_status}` : '',
    gate.coverage_status ? `coverage=${gate.coverage_status}` : '',
    gate.evidence_mix_status ? `mix=${gate.evidence_mix_status}` : '',
  ].filter(Boolean).join('；');
  if (statuses) lines.push(`- 子门禁：${statuses}`);
  const top = Number(gate.top_count || 0);
  if (top) lines.push(`- Top rerank 覆盖：${Number(gate.covered_top_count || 0)}/${top}，query coverage=${Number(gate.average_query_coverage || 0).toFixed(2)}`);
  if (Number(gate.total_required || 0)) lines.push(`- 覆盖审计：${Number(gate.covered_required || 0)}/${Number(gate.total_required || 0)}，ratio=${Number(gate.coverage_ratio || 0).toFixed(2)}`);
  if (Number(gate.mix_score || 0)) lines.push(`- 证据组合分：${Number(gate.mix_score || 0).toFixed(2)}`);
  lines.push(`- 建议：${gate.approval_hint || '批准进入 idea 前应先修复检索源或补 seed/query。'}`);
  return lines.join('\n');
}

function literatureEvidenceContractLabel(run) {
  const contract = run?.literature_evidence_contract;
  if (!contract?.status || contract.status === 'pass') return '';
  const blocking = Number(contract.blocking_issue_count || 0);
  const review = Number(contract.review_reason_count || 0);
  const citations = Number(contract.citations || 0);
  const chunks = Number(contract.chunks || 0);
  const substantive = Number(contract.citations_with_substantive_chunks || 0);
  const crossref = Number(contract.single_crossref_citations || 0);
  const parts = [citations || chunks ? `${citations}/${chunks}` : '', substantive ? `实${substantive}` : '', blocking ? `B${blocking}` : '', review ? `R${review}` : '', crossref ? `XRef${crossref}` : ''].filter(Boolean).join(' ');
  return parts ? `证据契约 ${contract.status} / ${parts}` : `证据契约 ${contract.status}`;
}

function literatureEvidenceContractDetails(run) {
  const contract = run?.literature_evidence_contract;
  if (!contract?.status || contract.status === 'pass') return '';
  const lines = ['文献证据契约摘要：'];
  lines.push(`- Citation/chunk：${Number(contract.citations || 0)} citations / ${Number(contract.chunks || 0)} chunks，coverage=${Number(contract.chunk_coverage || 0).toFixed(2)}`);
  lines.push(`- 实质证据片段：${Number(contract.citations_with_substantive_chunks || 0)}/${Number(contract.citations || 0)}，coverage=${Number(contract.substantive_chunk_coverage || 0).toFixed(2)}，median chars=${Number(contract.median_chunk_chars || 0)}`);
  lines.push(`- Locator：DOI=${Number(contract.doi_coverage || 0).toFixed(2)}，URL=${Number(contract.url_coverage || 0).toFixed(2)}，任一=${Number(contract.locator_coverage || 0).toFixed(2)}`);
  lines.push(`- 来源：diversity=${Number(contract.source_diversity || 0)}，single Crossref=${Number(contract.single_crossref_citations || 0)} (${Number(contract.single_crossref_ratio || 0).toFixed(2)})`);
  if (Array.isArray(contract.missing_evidence_roles) && contract.missing_evidence_roles.length) lines.push(`- 缺失证据角色：${contract.missing_evidence_roles.join(', ')}`);
  if (Number(contract.top_rerank_count || 0)) lines.push(`- Top rerank query 覆盖：${Number(contract.top_rerank_covered || 0)}/${Number(contract.top_rerank_count || 0)}，avg=${Number(contract.average_query_coverage || 0).toFixed(2)}`);
  const counts = [Number(contract.blocking_issue_count || 0) ? `阻断 ${Number(contract.blocking_issue_count || 0)}` : '', Number(contract.review_reason_count || 0) ? `复核 ${Number(contract.review_reason_count || 0)}` : '', Number(contract.required_action_count || 0) ? `动作 ${Number(contract.required_action_count || 0)}` : ''].filter(Boolean).join('，');
  if (counts) lines.push(`- 计数：${counts}`);
  lines.push('- 建议：批准前人工核对 Top DOI/URL、摘要或全文 chunk；block 状态先补 seed/fulltext 或重跑检索。');
  return lines.join('\n');
}

function literatureQualityGateLabel(run) {
  const gate = run?.literature_quality_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const selected = Number(gate.selected_papers || 0);
  const raw = Number(gate.raw_papers || 0);
  const missing = Array.isArray(gate.missing_roles) ? gate.missing_roles.length : 0;
  const queries = Number(gate.repair_queries || 0);
  const seeds = Number(gate.suggested_seed_count || 0);
  const parts = [raw || selected ? `${selected}/${raw}` : '', missing ? `缺${missing}` : '', queries ? `Q${queries}` : '', seeds ? `Seed${seeds}` : ''].filter(Boolean).join(' ');
  return parts ? `文献门禁 ${gate.status} / ${parts}` : `文献门禁 ${gate.status}`;
}

function literatureQualityGateDetails(run) {
  const gate = run?.literature_quality_gate;
  if (!gate?.status || gate.status === 'pass') return '';
  const lines = ['文献门禁摘要：'];
  const selected = Number(gate.selected_papers || 0);
  const raw = Number(gate.raw_papers || 0);
  if (raw || selected) lines.push(`- 文献筛选：${selected}/${raw}`);
  if (gate.quality_confidence) lines.push(`- 质量置信度：${gate.quality_confidence}`);
  if (gate.seed_role_coverage_status) lines.push(`- Seed 角色覆盖：${gate.seed_role_coverage_status}`);
  if (gate.evidence_contract_status) lines.push(`- 证据契约：${gate.evidence_contract_status}，block/review=${Number(gate.evidence_contract_blocking || 0)}/${Number(gate.evidence_contract_review || 0)}，chunk/locator=${Number(gate.evidence_contract_chunk_coverage || 0).toFixed(2)}/${Number(gate.evidence_contract_locator_coverage || 0).toFixed(2)}`);
  if (Array.isArray(gate.missing_roles) && gate.missing_roles.length) lines.push(`- 缺失角色：${gate.missing_roles.join(', ')}`);
  if (Number(gate.context_citations || 0) || Number(gate.context_chunks || 0)) lines.push(`- RAG context：${Number(gate.context_citations || 0)} citations / ${Number(gate.context_chunks || 0)} chunks`);
  if (gate.citation_grounding_status) lines.push(`- Citation grounding：${gate.citation_grounding_status}，block/review=${Number(gate.citation_grounding_blocked || 0)}/${Number(gate.citation_grounding_review || 0)}`);
  if (Number(gate.repair_queries || 0)) lines.push(`- 可回填补检索式：${gate.repair_queries}`);
  if (Number(gate.suggested_seed_count || 0)) lines.push(`- 可回填候选 seed：${gate.suggested_seed_count}`);
  lines.push(`- 建议：${gate.approval_hint || '批准进入 idea 前应填写审核意见或先应用检索建议。'}`);
  return lines.join('\n');
}

function repairQueueLabel(run) {
  const queue = run?.repair_queue;
  if (!queue?.status) return '';
  const block = Number(queue.block || 0);
  const high = Number(queue.high || 0);
  const medium = Number(queue.medium || 0);
  const items = Number(queue.items || 0);
  if (!items) return `修复 ${queue.status}`;
  return `修复 ${queue.status} / B${block} H${high} M${medium}`;
}

function repairResumeLabel(run) {
  const plan = run?.repair_resume_plan;
  if (!plan?.status) return '';
  const rerun = plan.rerun_from ? ` ${plan.rerun_from}` : '';
  const applied = plan.applied ? '已应用' : plan.can_resume ? '可恢复' : '预览';
  const tasks = Number(plan.repair_items || 0);
  const queries = Number(plan.retrieval_repair_tasks || 0);
  const approvals = [plan.review_reapproval_required ? 'R' : '', plan.execution_reapproval_required ? 'E' : ''].filter(Boolean).join('');
  const parts = [tasks ? `T${tasks}` : '', queries ? `Q${queries}` : '', approvals ? `G${approvals}` : ''].filter(Boolean).join(' ');
  return parts ? `修复恢复 ${applied}${rerun} / ${parts}` : `修复恢复 ${applied}${rerun}`;
}

function goldRunDoctorLabel(run) {
  const doctor = run?.gold_run_doctor;
  if (!doctor?.status) return '';
  const checks = doctor.check_status_counts || {};
  const preflight = doctor.preflight_status_counts || {};
  const failedChecks = Number(checks.fail || 0) + Number(checks.block || 0);
  const warnChecks = Number(checks.warn || 0);
  const failedPreflight = Number(preflight.fail || 0) + Number(preflight.block || 0);
  const warnPreflight = Number(preflight.warn || 0);
  const repairItems = Number(doctor.candidate_repair_plan_items || 0);
  const resume = doctor.candidate_repair_resume_plan || {};
  const launch = doctor.launch_status ? `L:${doctor.launch_status}` : '';
  const parts = [
    doctor.preflight_status ? `PF:${doctor.preflight_status}` : '',
    launch,
    doctor.can_start_gold_run ? '可启动' : '',
    failedPreflight ? `PFB${failedPreflight}` : '',
    warnPreflight ? `PFW${warnPreflight}` : '',
    failedChecks ? `B${failedChecks}` : '',
    warnChecks ? `W${warnChecks}` : '',
    repairItems ? `T${repairItems}` : '',
    resume.status ? `恢复${resume.status}` : '',
    resume.can_resume ? '可恢复' : '',
  ].filter(Boolean).join(' ');
  return parts ? `Gold Doctor ${doctor.status} / ${parts}` : `Gold Doctor ${doctor.status}`;
}

function goldRunVerifyLabel(run) {
  const verify = run?.gold_run_verification;
  if (!verify?.status) return '';
  const missing = Number(verify.missing_artifact_count || 0);
  const repairs = Number(verify.repair_plan_items || 0);
  const ready = verify.gold_contract_ready ? 'ready' : verify.status;
  const parts = [missing ? `M${missing}` : '', repairs ? `T${repairs}` : ''].filter(Boolean).join(' ');
  return parts ? `Gold Verify ${ready} / ${parts}` : `Gold Verify ${ready}`;
}

function goldVerifyFollowupLines(result) {
  const lines = [];
  if (result?.wrote_artifacts) {
    lines.push('- 写入：15-gold-run-verification.md/json');
  }
  const plan = result?.repair_resume_plan || {};
  if (plan.status) {
    const tasks = Number(plan.repair_items || 0);
    const rerun = plan.rerun_from ? `，rerun_from=${plan.rerun_from}` : '';
    const gates = [plan.review_reapproval_required ? 'review' : '', plan.execution_reapproval_required ? 'execution' : ''].filter(Boolean);
    lines.push(`- 修复恢复：${plan.status}，tasks=${tasks}${rerun}${gates.length ? `，重新批准=${gates.join('+')}` : ''}`);
  }
  if (result?.perfect_readiness_written) {
    lines.push('- Perfect readiness：已刷新');
  }
  const post = result?.gold_post_launch || {};
  if (post.status) {
    lines.push(`- Post-launch：${post.status}，verification artifacts=${Number(post.verification_artifact_count || 0)}，repair artifacts=${Number(post.repair_resume_plan_artifact_count || 0)}`);
  }
  return lines.length ? ['Post-verify', ...lines].join('\n') : '';
}

function repairResolutionLabel(run) {
  const audit = run?.repair_resolution;
  if (!audit?.status || audit.status === 'not_applicable') return '';
  const remaining = Number(audit.remaining_items || 0);
  const resolved = Number(audit.resolved_items || 0);
  const blocking = Number(audit.blocking_issue_count || 0);
  const manual = Number(audit.manual_task_count || 0);
  const score = Number.isFinite(Number(audit.resolution_score)) ? ` ${Number(audit.resolution_score).toFixed(2)}` : '';
  const parts = [remaining ? `剩${remaining}` : '', resolved ? `闭${resolved}` : '', blocking ? `B${blocking}` : '', manual ? `M${manual}` : ''].filter(Boolean).join(' ');
  return parts ? `修复闭环 ${audit.status}${score} / ${parts}` : `修复闭环 ${audit.status}${score}`;
}

function literatureRepairLabel(run) {
  const strategy = run?.literature_search_strategy;
  const feedback = run?.literature_search_feedback;
  if (strategy?.status && !['pass', ''].includes(strategy.status)) {
    const missing = Array.isArray(strategy.missing_required_intents) ? strategy.missing_required_intents.length : 0;
    const weak = Number(strategy.weak_selected_queries || 0);
    return `检索策略 ${strategy.status} / 缺${missing} 弱${weak}`;
  }
  if (!feedback?.status || ['pass', 'ready_for_review'].includes(feedback.status)) return '';
  const queries = Number(feedback.recommended_queries || 0);
  const seeds = Number(feedback.seed_targets || 0);
  const agentQueries = Number(feedback.agent_queries || 0);
  return `检索修复 ${feedback.status} / Q${queries} Seed${seeds} Agent${agentQueries}`;
}

function literatureRescuePlanLabel(run) {
  const rescue = run?.literature_rescue_plan;
  if (!rescue?.status || ['pass', 'not_applicable'].includes(rescue.status)) return '';
  const queries = Number(rescue.rescue_queries || 0);
  const roles = Array.isArray(rescue.missing_evidence_roles) ? rescue.missing_evidence_roles.length : 0;
  const sources = Number(rescue.source_repairs || 0);
  const parts = [queries ? `Q${queries}` : '', roles ? `Role${roles}` : '', sources ? `Src${sources}` : ''].filter(Boolean).join(' ');
  return parts ? `补检索计划 ${rescue.status} / ${parts}` : `补检索计划 ${rescue.status}`;
}

function literatureRescueExecutionLabel(run) {
  const execution = run?.literature_rescue_execution;
  if (!execution?.status || ['skipped', 'not_applicable'].includes(execution.status)) return '';
  const unresolved = Number(execution.unresolved_query_outcomes || 0);
  const closed = Number(execution.closed_query_outcomes || 0);
  const fresh = Number(execution.new_unique_papers || 0);
  const parts = [unresolved ? `U${unresolved}` : '', closed ? `C${closed}` : '', fresh ? `N${fresh}` : ''].filter(Boolean).join(' ');
  return parts ? `补检索执行 ${execution.status} / ${parts}` : `补检索执行 ${execution.status}`;
}

function seedIntakeLabel(run) {
  const seed = run?.seed_intake;
  if (!seed?.status && !seed?.role_coverage_status) return '';
  const status = String(seed.status || '');
  const roleStatus = String(seed.role_coverage_status || '');
  const statusOk = ['', 'pass', 'not_configured', 'not_applicable'].includes(status);
  const rolesOk = ['', 'pass', 'not_applicable'].includes(roleStatus);
  const total = Number(seed.total_seed_entries || 0);
  const curated = Number(seed.curated_seed_papers || 0);
  const missing = Array.isArray(seed.missing_roles) ? seed.missing_roles.length : Number(seed.missing_roles || 0);
  const suggested = Number(seed.suggested_seed_count || 0);
  if (statusOk && rolesOk && !suggested) return '';
  const suggestedRoles = seed.suggested_seed_role_counts || {};
  const suggestedRoleCount = ['review', 'benchmark_dataset', 'baseline_method', 'recent'].filter((role) => Number(suggestedRoles[role] || 0) > 0).length;
  const role = roleStatus && roleStatus !== status ? ` 角色${roleStatus}` : '';
  const coverage = total ? ` ${curated}/${total}` : '';
  const missingText = missing ? ` 缺${missing}` : '';
  const suggestedText = suggested ? ` 建议${suggested}${suggestedRoleCount ? `/R${suggestedRoleCount}` : ''}` : '';
  return `Seed ${status || '-'}${role}${coverage}${missingText}${suggestedText}`;
}

function runIntegrityLabel(run) {
  const integrity = run?.run_integrity;
  if (!integrity?.status) return '';
  const block = Number(integrity.blocking_issues || integrity.block || 0);
  const warn = Number(integrity.warnings || integrity.warn || 0);
  const pass = Number(integrity.pass || 0);
  const parts = [block ? `B${block}` : '', warn ? `W${warn}` : '', pass ? `P${pass}` : ''].filter(Boolean).join(' ');
  return parts ? `完整性 ${integrity.status} / ${parts}` : `完整性 ${integrity.status}`;
}

function finalHandoffLabel(run) {
  const handoff = run?.final_handoff;
  if (!handoff?.status) return '';
  const blocking = Number(handoff.blocking_issues || 0);
  const manual = Number(handoff.manual_tasks || 0);
  const audit = handoff.package_has_integrity_audit ? 'A✓' : 'A-';
  const zip = typeof handoff.package_zip_valid === 'boolean' ? (handoff.package_zip_valid ? 'Z✓' : 'Z!') : '';
  const parts = [blocking ? `B${blocking}` : '', manual ? `M${manual}` : '', audit, zip].filter(Boolean).join(' ');
  return parts ? `交付 ${handoff.status} / ${parts}` : `交付 ${handoff.status}`;
}

function agentTrajectoryLabel(run) {
  const trajectory = run?.agent_trajectory;
  if (!trajectory?.status) return '';
  const pass = Number(trajectory.pass || 0);
  const warn = Number(trajectory.warn || 0);
  const block = Number(trajectory.block || 0);
  const notStarted = Number(trajectory.not_started || 0);
  const manual = Number(trajectory.manual_tasks || 0);
  const backfilled = Number(trajectory.backfilled_events || 0);
  const last = String(trajectory.last_event || '').trim();
  const parts = [
    pass ? `P${pass}` : '',
    warn ? `W${warn}` : '',
    block ? `B${block}` : '',
    notStarted ? `N${notStarted}` : '',
    manual ? `M${manual}` : '',
    last ? `last=${last}` : '',
    backfilled ? `BF${backfilled}` : '',
  ].filter(Boolean).join(' ');
  return parts ? `轨迹 ${trajectory.status} / ${parts}` : `轨迹 ${trajectory.status}`;
}

function agentObservabilityLabel(run) {
  const audit = run?.agent_observability;
  if (!audit?.status) return '';
  const events = Number(audit.manifest_events || 0);
  const artifacts = Number(audit.manifest_artifacts || 0);
  const failed = Number(audit.llm_failed_calls || 0);
  const budget = Number(audit.llm_budget_exceeded_calls || 0);
  const experiments = Number(audit.experiment_runs || 0);
  const blocking = Number(audit.blocking_issue_count || 0);
  const manual = Number(audit.manual_task_count || 0);
  const warnings = Number(audit.warnings || 0);
  const repair = String(audit.repair_queue_status || '').trim();
  const pressure = Math.max(Number(audit.call_utilization || 0), Number(audit.prompt_utilization || 0));
  const parts = [
    events ? `E${events}` : '',
    artifacts ? `A${artifacts}` : '',
    failed ? `L${failed}` : '',
    budget ? `Q${budget}` : '',
    experiments ? `X${experiments}` : '',
    repair ? `R${repair}` : '',
    blocking ? `B${blocking}` : '',
    manual ? `M${manual}` : '',
    warnings ? `W${warnings}` : '',
    pressure ? `p${pressure.toFixed(2)}` : '',
  ].filter(Boolean).join(' ');
  return parts ? `可观测 ${audit.status} / ${parts}` : `可观测 ${audit.status}`;
}

function humanGateAuditLabel(run) {
  const audit = run?.human_gate_audit;
  if (!audit?.status || audit.status === 'pass') return '';
  const downstream = Number(audit.downstream_artifacts || 0);
  const execution = Number(audit.execution_artifacts || 0);
  const blocking = Number(audit.blocking_issue_count || 0);
  const manual = Number(audit.manual_task_count || 0);
  const review = audit.review_approved ? 'R✓' : 'R-';
  const exec = audit.execution_approved ? 'E✓' : 'E-';
  const reapproval = [audit.review_reapproval_required ? 'R' : '', audit.execution_reapproval_required ? 'E' : ''].filter(Boolean).join('');
  const repair = audit.repair_resume_applied ? `G${reapproval || '!'}` : reapproval ? `g${reapproval}` : '';
  const parts = [review, exec, repair, downstream ? `D${downstream}` : '', execution ? `X${execution}` : '', blocking ? `B${blocking}` : '', manual ? `M${manual}` : ''].filter(Boolean).join(' ');
  return parts ? `人工Gate ${audit.status} / ${parts}` : `人工Gate ${audit.status}`;
}

function llmRuntimeContractLabel(run) {
  const contract = run?.llm_runtime_contract;
  if (!contract?.status || contract.status === 'pass') return '';
  const calls = Number(contract.total_calls || 0);
  const blocking = Number(contract.blocking_issue_count || 0);
  const manual = Number(contract.manual_task_count || 0);
  const warnings = Number(contract.warning_count || 0);
  const model = contract.model_configured ? 'M✓' : 'M-';
  const budget = contract.call_budget_configured || contract.prompt_budget_configured ? 'Q✓' : 'Q-';
  const key = contract.api_key_persisted ? 'K!' : '';
  const parts = [model, budget, key, calls ? `C${calls}` : '', blocking ? `B${blocking}` : '', manual ? `M${manual}` : '', warnings ? `W${warnings}` : ''].filter(Boolean).join(' ');
  return parts ? `LLM契约 ${contract.status} / ${parts}` : `LLM契约 ${contract.status}`;
}

function llmObservabilityLabel(run) {
  const summary = run?.llm_observability;
  if (!summary?.status || summary.status === 'pass') return '';
  const passed = Number(summary.passed_required || 0);
  const required = Number(summary.required_stages || 0);
  const missing = Number(summary.missing_required_stage_count || 0);
  const calls = Number(summary.total_calls || 0);
  const failed = Number(summary.failed_calls || 0);
  const budget = Number(summary.budget_exceeded_calls || 0);
  const missingNames = Array.isArray(summary.missing_required_stages) && summary.missing_required_stages.length
    ? ` ${summary.missing_required_stages.slice(0, 2).join(',')}`
    : '';
  const parts = [required ? `S${passed}/${required}` : '', missing ? `G${missing}${missingNames}` : '', calls ? `C${calls}` : '', failed ? `F${failed}` : '', budget ? `Q${budget}` : ''].filter(Boolean).join(' ');
  return parts ? `LLM总览 ${summary.status} / ${parts}` : `LLM总览 ${summary.status}`;
}

function openSourceComplianceLabel(run) {
  const summary = run?.open_source_compliance;
  if (!summary?.status || summary.status === 'pass') return '';
  const projects = Number(summary.project_count || 0);
  const blockedProjects = Number(summary.blocked_project_count || 0);
  const warnProjects = Number(summary.warn_project_count || 0);
  const blocked = Number(summary.blocking_issue_count ?? summary.blocking_issues ?? 0);
  const manual = Number(summary.manual_task_count ?? summary.manual_tasks ?? 0);
  const parts = [projects ? `P${projects}` : '', blockedProjects ? `B${blockedProjects}` : '', warnProjects ? `W${warnProjects}` : '', blocked ? `I${blocked}` : '', manual ? `M${manual}` : ''].filter(Boolean).join(' ');
  return parts ? `开源 ${summary.status} / ${parts}` : `开源 ${summary.status}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {'Content-Type': 'application/json'},
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromResponse(text, response.status));
  }
  return response.json();
}

function publicGoldLaunchCommands(commands) {
  if (!Array.isArray(commands)) return [];
  return commands
    .map((command) => String(command || '').trim())
    .filter((command) => command && !command.startsWith('export '))
    .map((command) => command.replace(/sk-[A-Za-z0-9_-]{8,}/g, 'sk-<redacted>'))
    .slice(0, 8);
}

function goldEnvironmentSafeCommands(report) {
  if (!report || typeof report !== 'object') return [];
  const values = [];
  if (report.safe_commands && typeof report.safe_commands === 'object') {
    values.push(...Object.values(report.safe_commands));
  }
  if (Array.isArray(report.launch_plan?.safe_commands)) {
    values.push(...report.launch_plan.safe_commands);
  }
  return publicGoldLaunchCommands(values);
}

function goldEnvironmentActionMarkdown(report) {
  if (!report || typeof report !== 'object') return '';
  const reports = report.reports && typeof report.reports === 'object' ? report.reports : {};
  const goldEnv = reports.gold_env && typeof reports.gold_env === 'object' ? reports.gold_env : {};
  const serverEnv = report.server_environment && typeof report.server_environment === 'object'
    ? report.server_environment
    : goldEnv.server_environment && typeof goldEnv.server_environment === 'object'
      ? goldEnv.server_environment
      : {};
  const focus = String(report.prelaunch_focus?.category || '').trim();
  const readyExceptEnvironment = report.ready_except_server_environment === true
    || report.prelaunch_focus?.ready_except_server_environment === true;
  const missing = Array.isArray(serverEnv.missing_required) ? serverEnv.missing_required.map(safeLaunchText).filter(Boolean) : [];
  const invalid = Array.isArray(serverEnv.invalid_required) ? serverEnv.invalid_required.map(safeLaunchText).filter(Boolean) : [];
  const envStatus = String(serverEnv.status || '').trim();
  const blockedByEnvironment = readyExceptEnvironment
    || focus === 'server_environment'
    || envStatus === 'needs_server_environment'
    || missing.length
    || invalid.length;
  if (!blockedByEnvironment) return '';

  const present = Number(serverEnv.required_present || 0);
  const total = Number(serverEnv.required_total || 0);
  const gateway = serverEnv.gateway_socket && typeof serverEnv.gateway_socket === 'object' ? serverEnv.gateway_socket : {};
  const gatewayStatus = safeLaunchText(gateway.status || '');
  const commands = goldEnvironmentSafeCommands(report);
  const recommendedCommand = commands.find((command) => command.includes('scripts/start_gold_web_env.sh'))
    || commands.find((command) => command.includes('scripts/run_gold_cli_env.sh'))
    || '';
  return [
    '## Server Environment Action',
    readyExceptEnvironment
      ? '- 本地 gold defaults 已就绪；当前只差 Web 服务进程的 server environment。'
      : '- Gold run 被 Web 服务进程的 server environment 阻断。',
    total ? `- 服务端环境：${present}/${total}${envStatus ? `；status=${envStatus}` : ''}` : '',
    missing.length ? `- 缺失必填：${missing.join(', ')}` : '',
    invalid.length ? `- 无效必填：${invalid.join(', ')}` : '',
    gatewayStatus ? `- Gateway socket：${gatewayStatus}` : '',
    '- 在本机终端运行安全入口，按提示输入真实 contact email 和 hidden API key。',
    '- 不要把 secret 粘贴到 Web 表单；服务重启后再运行 Gold Smoke 或 Gold Bundle。',
    recommendedCommand ? `- 推荐命令：${recommendedCommand}` : '',
  ].filter(Boolean).join('\n');
}

function payloadForRunAction() {
  const payload = payloadFromForm();
  if (payload.paper_grade_enabled === true) {
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
  }
  return payload;
}

function payloadForCurrentRunAction({notesOnly = false} = {}) {
  const current = payloadForRunAction();
  const payload = {review_notes: current.review_notes || ''};
  if (notesOnly || state.currentRun?.worker_active === true) return payload;

  const baseline = state.formConfigRunId === state.currentRun?.id ? state.runActionBaseline : null;
  if (baseline) {
    for (const field of RUN_ACTION_CONFIG_FIELDS) {
      if (current[field] !== baseline[field]) payload[field] = current[field];
    }
  }
  for (const field of RUN_ACTION_REENTERED_FIELDS) {
    if (String(current[field] || '').trim()) payload[field] = current[field];
  }
  return payload;
}

function publicGoldLaunchChecklist(items) {
  if (!Array.isArray(items)) return [];
  return items.slice(0, 12)
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const status = ['pass', 'warn', 'review', 'block', 'fail'].includes(String(item.status || '')) ? String(item.status) : 'other';
      const formFields = Array.isArray(item.form_fields)
        ? item.form_fields.map((field) => String(field || '').trim()).filter((field) => /^[a-z0-9_]+$/i.test(field)).slice(0, 8)
        : [];
      return {
        item: safeLaunchText(item.item),
        status,
        button: safeLaunchText(item.button),
        form_fields: formFields,
        next_step: safeLaunchText(item.next_step),
      };
    })
    .filter((item) => item.item);
}

function publicGoldLaunchReadiness(readiness) {
  const data = readiness && typeof readiness === 'object' ? readiness : {};
  const status = ['ready_to_start', 'blocked', 'needs_review'].includes(String(data.status || ''))
    ? String(data.status)
    : 'needs_review';
  const blockingItems = Array.isArray(data.blocking_items)
    ? data.blocking_items.map(safeLaunchText).filter(Boolean).slice(0, 12)
    : [];
  const reviewItems = Array.isArray(data.review_items)
    ? data.review_items.map(safeLaunchText).filter(Boolean).slice(0, 12)
    : [];
  return {
    status,
    can_start_gold_run: data.can_start_gold_run === true,
    blocking_items: blockingItems,
    review_items: reviewItems,
    secret_policy: String(data.secret_policy || '') === 'move_secrets_to_env' ? 'move_secrets_to_env' : 'env_only',
    safe_launch_command_count: Number(data.safe_launch_command_count || 0),
  };
}

function safeLaunchText(value) {
  return String(value || '')
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, 'sk-<redacted>')
    .replace(/\b[A-Z][A-Z0-9_]*API_KEY\b/g, '<secret-env>')
    .replace(/[\r\n]+/g, ' ')
    .trim()
    .slice(0, 260);
}

function updateGoldLaunchPanelVisibility() {
  if (!els.goldLaunchCommandPanel) return;
  els.goldLaunchCommandPanel.hidden = !state.goldLaunchCommands.length && !state.goldLaunchChecklist.length;
}

function clearGoldLaunchCommands() {
  state.goldLaunchCommands = [];
  state.goldLaunchChecklist = [];
  if (els.goldLaunchChecklist) {
    els.goldLaunchChecklist.hidden = true;
    els.goldLaunchChecklist.innerHTML = '';
  }
  if (els.goldLaunchCommandText) els.goldLaunchCommandText.textContent = '';
  if (els.copyGoldLaunchCommands) {
    els.copyGoldLaunchCommands.disabled = true;
    els.copyGoldLaunchCommands.textContent = '复制';
  }
  updateGoldLaunchPanelVisibility();
}

function renderGoldLaunchCommands(commands) {
  const publicCommands = publicGoldLaunchCommands(commands);
  state.goldLaunchCommands = publicCommands;
  if (!els.goldLaunchCommandText || !els.copyGoldLaunchCommands) return;
  if (publicCommands.length) {
    els.goldLaunchCommandText.textContent = publicCommands.join('\n');
    els.copyGoldLaunchCommands.disabled = false;
    els.copyGoldLaunchCommands.textContent = '复制';
  } else {
    els.goldLaunchCommandText.textContent = '';
    els.copyGoldLaunchCommands.disabled = true;
  }
  updateGoldLaunchPanelVisibility();
}

function renderGoldLaunchChecklist(items) {
  const publicItems = publicGoldLaunchChecklist(items);
  state.goldLaunchChecklist = publicItems;
  if (!els.goldLaunchChecklist) return;
  if (!publicItems.length) {
    els.goldLaunchChecklist.hidden = true;
    els.goldLaunchChecklist.innerHTML = '';
    updateGoldLaunchPanelVisibility();
    return;
  }
  els.goldLaunchChecklist.hidden = false;
  els.goldLaunchChecklist.innerHTML = publicItems.map((item) => {
    const fields = item.form_fields.length ? `fields: ${item.form_fields.join(', ')}` : '';
    const button = item.button ? `button: ${item.button}` : '';
    const meta = [button, fields].filter(Boolean).join(' | ');
    return `
      <div class="launch-checklist-item">
        <div class="launch-checklist-title">
          <span class="launch-checklist-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
          <span>${escapeHtml(item.item)}</span>
        </div>
        ${meta ? `<div class="launch-checklist-meta">${escapeHtml(meta)}</div>` : ''}
        ${item.next_step ? `<div class="launch-checklist-meta">${escapeHtml(item.next_step)}</div>` : ''}
      </div>
    `;
  }).join('');
  updateGoldLaunchPanelVisibility();
}

async function copyGoldLaunchCommands() {
  const text = state.goldLaunchCommands.join('\n');
  if (!text || !els.copyGoldLaunchCommands) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
  els.copyGoldLaunchCommands.textContent = '已复制';
  window.setTimeout(() => {
    if (els.copyGoldLaunchCommands) els.copyGoldLaunchCommands.textContent = '复制';
  }, 1200);
}

function clearGoldLaunchCommandsWhenArtifactChanges() {
  if (String(els.artifactTitle?.textContent || '').startsWith('gold doctor')) return;
  clearGoldLaunchCommands();
}

function errorMessageFromResponse(text, status) {
  if (!text) return `HTTP ${status}`;
  try {
    const data = JSON.parse(text);
    if (data.markdown) return data.markdown;
    if (typeof data.error === 'string') return data.error;
    if (data.error && typeof data.error === 'object') {
      return String(data.error.message || data.error.detail || JSON.stringify(data.error));
    }
  } catch (error) {
    return text;
  }
  return text;
}

function runRefreshSignature(run) {
  if (!run) return '';
  return JSON.stringify([
    run.id,
    run.status,
    run.stage,
    run.worker_active === true,
    run.updated_at || '',
    Array.isArray(run.artifacts) ? run.artifacts : [],
  ]);
}

function runStatusSignature(run) {
  if (!run) return '';
  return JSON.stringify([run.id, run.status, run.stage, run.worker_active === true, run.updated_at || '']);
}

async function refreshRuns(keepSelection = true, forceArtifact = false) {
  const refreshSequence = ++state.runsRefreshSequence;
  const runLoadSequence = state.runLoadSequence;
  const previousRun = state.currentRun;
  const previousSignature = runRefreshSignature(previousRun);
  const data = await api('/api/runs?view=summary');
  if (refreshSequence !== state.runsRefreshSequence) return;
  state.runs = Array.isArray(data.runs) ? data.runs : [];

  if (runLoadSequence !== state.runLoadSequence) {
    renderRunList();
    return;
  }

  const selectedId = keepSelection ? state.currentRun?.id : null;
  let selected = (selectedId && state.runs.find((run) => run.id === selectedId)) || state.runs[0] || null;
  if (selected && state.currentRun?.id === selected.id) {
    if (runStatusSignature(selected) !== runStatusSignature(state.currentRun)) {
      selected = await api(`/api/runs/${encodeURIComponent(selected.id)}`);
      if (refreshSequence !== state.runsRefreshSequence || runLoadSequence !== state.runLoadSequence) return;
    } else {
      selected = {...state.currentRun, ...selected};
    }
  } else if (selected && !selected.config) {
    const detail = await api(`/api/runs/${encodeURIComponent(selected.id)}`);
    if (refreshSequence !== state.runsRefreshSequence || runLoadSequence !== state.runLoadSequence) return;
    selected = detail;
  }
  setCurrentRun(selected);
  renderRunList();
  const runChanged = previousRun?.id !== state.currentRun?.id || previousSignature !== runRefreshSignature(state.currentRun);
  if (state.currentRun && (forceArtifact || runChanged)) await loadArtifact(state.selectedFile);
}

async function loadRunSummary() {
  els.summary.disabled = true;
  const previousText = els.summary.textContent;
  els.summary.textContent = '生成中';
  try {
    const result = await api('/api/summary');
    els.artifactTitle.textContent = 'runs-summary / memory';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.dashboard || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'runs-summary / memory';
    els.artifactContent.textContent = `对比失败：${error.message}`;
  } finally {
    els.summary.disabled = false;
    els.summary.textContent = previousText;
  }
}

async function loadPlatformAudit() {
  els.platformAudit.disabled = true;
  const previousText = els.platformAudit.textContent;
  els.platformAudit.textContent = '审计中';
  try {
    const result = await api('/api/platform-audit');
    els.artifactTitle.textContent = 'runs-platform-audit';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.audit || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'runs-platform-audit';
    els.artifactContent.textContent = `平台审计失败：${error.message}`;
  } finally {
    els.platformAudit.disabled = false;
    els.platformAudit.textContent = previousText;
  }
}

async function loadPerfectReadiness() {
  els.perfectReadiness.disabled = true;
  const previousText = els.perfectReadiness.textContent;
  els.perfectReadiness.textContent = '检查中';
  try {
    const result = await api('/api/perfect-readiness');
    const status = result.report?.status || 'unknown';
    const score = Number.isFinite(Number(result.report?.score)) ? ` ${Number(result.report.score).toFixed(3)}` : '';
    els.artifactTitle.textContent = `perfect-readiness: ${status}${score}`;
    els.downloadLink.href = '#';
    const md = result.markdown || JSON.stringify(result.report || result, null, 2);
    els.artifactContent.textContent = md;
    const readinessBox = document.querySelector('#readiness-details-content');
    if (readinessBox) readinessBox.innerHTML = formatAcademicMarkdown(md, 'perfect-readiness.md');
  } catch (error) {
    els.artifactTitle.textContent = 'perfect-readiness';
    els.artifactContent.textContent = `完美度检查失败：${error.message}`;
  } finally {
    els.perfectReadiness.disabled = false;
    els.perfectReadiness.textContent = previousText;
  }
}

async function previewOpenSourceBackfill() {
  els.openSourceBackfillPreview.disabled = true;
  const previousText = els.openSourceBackfillPreview.textContent;
  els.openSourceBackfillPreview.textContent = '预览中';
  try {
    const result = await api('/api/open-source-compliance-backfill');
    els.artifactTitle.textContent = 'open-source-compliance-backfill preview';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'open-source-compliance-backfill';
    els.artifactContent.textContent = `开源合规回填预览失败：${error.message}`;
  } finally {
    els.openSourceBackfillPreview.disabled = false;
    els.openSourceBackfillPreview.textContent = previousText;
  }
}

async function runOpenSourceBackfill() {
  els.openSourceBackfillRun.disabled = true;
  const previousText = els.openSourceBackfillRun.textContent;
  els.openSourceBackfillRun.textContent = '回填中';
  try {
    const result = await api('/api/open-source-compliance-backfill', {
      method: 'POST',
      body: JSON.stringify({dry_run: false, force: false}),
    });
    els.artifactTitle.textContent = 'open-source-compliance-backfill';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || JSON.stringify(result.report || result, null, 2),
      '',
      '已写入缺失的开源经验/合规产物；没有启动研究、批准 review gate 或执行实验。',
    ].join('\n');
    await refreshRuns(true);
  } catch (error) {
    els.artifactTitle.textContent = 'open-source-compliance-backfill';
    els.artifactContent.textContent = `开源合规回填失败：${error.message}`;
  } finally {
    els.openSourceBackfillRun.disabled = false;
    els.openSourceBackfillRun.textContent = previousText;
  }
}

async function previewLlmObservabilityBackfill() {
  els.llmBackfillPreview.disabled = true;
  const previousText = els.llmBackfillPreview.textContent;
  els.llmBackfillPreview.textContent = '预览中';
  try {
    const result = await api('/api/llm-observability-backfill');
    els.artifactTitle.textContent = 'llm-observability-backfill preview';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'llm-observability-backfill';
    els.artifactContent.textContent = `LLM 审计回填预览失败：${error.message}`;
  } finally {
    els.llmBackfillPreview.disabled = false;
    els.llmBackfillPreview.textContent = previousText;
  }
}

async function runLlmObservabilityBackfill() {
  els.llmBackfillRun.disabled = true;
  const previousText = els.llmBackfillRun.textContent;
  els.llmBackfillRun.textContent = '回填中';
  try {
    const result = await api('/api/llm-observability-backfill', {
      method: 'POST',
      body: JSON.stringify({dry_run: false, force: false}),
    });
    els.artifactTitle.textContent = 'llm-observability-backfill';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || JSON.stringify(result.report || result, null, 2),
      '',
      '已写入缺失的 LLM trace/economics/observability 审计产物；没有创建 LLM 账本、启动研究、批准 review gate 或执行实验。',
    ].join('\n');
    await refreshRuns(true);
  } catch (error) {
    els.artifactTitle.textContent = 'llm-observability-backfill';
    els.artifactContent.textContent = `LLM 审计回填失败：${error.message}`;
  } finally {
    els.llmBackfillRun.disabled = false;
    els.llmBackfillRun.textContent = previousText;
  }
}

async function previewRepairResumeBackfill() {
  els.repairBackfillPreview.disabled = true;
  const previousText = els.repairBackfillPreview.textContent;
  els.repairBackfillPreview.textContent = '预览中';
  try {
    const result = await api('/api/repair-resume-backfill');
    els.artifactTitle.textContent = 'repair-resume-backfill preview';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'repair-resume-backfill';
    els.artifactContent.textContent = `修复预案回填预览失败：${error.message}`;
  } finally {
    els.repairBackfillPreview.disabled = false;
    els.repairBackfillPreview.textContent = previousText;
  }
}

async function runRepairResumeBackfill() {
  els.repairBackfillRun.disabled = true;
  const previousText = els.repairBackfillRun.textContent;
  els.repairBackfillRun.textContent = '回填中';
  try {
    const result = await api('/api/repair-resume-backfill', {
      method: 'POST',
      body: JSON.stringify({dry_run: false, force: false}),
    });
    els.artifactTitle.textContent = 'repair-resume-backfill';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || JSON.stringify(result.report || result, null, 2),
      '',
      '已为 active repair queue 写入缺失的修复恢复预案；没有删除产物、恢复 pipeline、批准 gate 或执行实验。',
    ].join('\n');
    await refreshRuns(true);
  } catch (error) {
    els.artifactTitle.textContent = 'repair-resume-backfill';
    els.artifactContent.textContent = `修复预案回填失败：${error.message}`;
  } finally {
    els.repairBackfillRun.disabled = false;
    els.repairBackfillRun.textContent = previousText;
  }
}

async function loadRepairResumeBacklog() {
  els.repairBacklog.disabled = true;
  const previousText = els.repairBacklog.textContent;
  els.repairBacklog.textContent = '读取中';
  try {
    const result = await api('/api/repair-resume-backlog');
    els.artifactTitle.textContent = 'repair-resume-backlog';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || JSON.stringify(result.report || result, null, 2),
      '',
      '只读取修复 backlog；没有删除产物、批准 gate、恢复 pipeline 或执行实验。',
    ].join('\n');
  } catch (error) {
    els.artifactTitle.textContent = 'repair-resume-backlog';
    els.artifactContent.textContent = `修复 Backlog 读取失败：${error.message}`;
  } finally {
    els.repairBacklog.disabled = false;
    els.repairBacklog.textContent = previousText;
  }
}

async function applyMemoryDefaultsToForm() {
  els.applyMemoryDefaults.disabled = true;
  const previousText = els.applyMemoryDefaults.textContent;
  els.applyMemoryDefaults.textContent = '应用中...';
  try {
    const result = await api('/api/summary');
    const config = result.memory?.recommended_config || {};
    const applied = [];
    const notes = [];

    if (config.literature_provider) {
      setFieldValue('literature_provider', config.literature_provider);
      applied.push(`文献模式=${config.literature_provider}`);
    }
    if (Array.isArray(config.sources) && config.sources.length) {
      setFieldValue('literature_sources', config.sources.join(', '));
      applied.push(`sources=${config.sources.join(', ')}`);
    }
    if (Number(config.max_papers || 0)) {
      setNumberMinimum('max_papers', Number(config.max_papers));
      applied.push(`max_papers>=${config.max_papers}`);
    }
    if (Number(config.max_search_queries || 0)) {
      setNumberMinimum('max_search_queries', Number(config.max_search_queries));
      applied.push(`max_search_queries>=${config.max_search_queries}`);
    }
    if (Array.isArray(config.extra_search_queries) && config.extra_search_queries.length) {
      const added = appendTextareaLines('extra_search_queries', config.extra_search_queries);
      if (added.length) applied.push(`补充检索式+${added.length}`);
    }
    if (config.manual_seed_required) {
      const minimum = Number(config.seed_papers_min || 3);
      notes.push(`仍需人工填写至少 ${minimum} 篇高相关 DOI/URL seed papers。`);
    }
    const missingRequiredReleaseFields = missingReleaseFormFields(config.release_required_fields);
    if (missingRequiredReleaseFields.length) {
      notes.push(`Release 必填仍需人工填写：${missingRequiredReleaseFields.map(releaseFieldLabel).join('、')}。`);
    }
    const missingRecommendedReleaseFields = missingReleaseFormFields(config.release_recommended_fields);
    if (missingRecommendedReleaseFields.length) {
      notes.push(`Release 推荐补充：${missingRecommendedReleaseFields.map(releaseFieldLabel).join('、')}。`);
    }
    const releaseCliArgs = Array.isArray(config.release_cli_args)
      ? config.release_cli_args.map((item) => String(item).trim()).filter(Boolean)
      : [];
    if (releaseCliArgs.length) {
      notes.push(`CLI 等价参数：${releaseCliArgs.join(' ')}`);
    }
    if (config.semantic_scholar_api_key_required) {
      notes.push('历史运行出现 Semantic Scholar 限流；有 key 后再加入 semantic_scholar。');
    }
    if (config.contact_email_required) {
      notes.push('建议填写文献源邮箱，提高 OpenAlex/Crossref/PubMed 请求稳定性。');
    }

    els.artifactTitle.textContent = '历史推荐已应用';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = applied.length || notes.length
      ? ['已写入左侧表单/待办提示：', ...applied.map((item) => `- ${item}`), '', ...notes, '', '这只更新表单配置，不会启动研究、批准 review gate 或执行 gate；启动前请重新预检配置并人工核对 seed、query、文献源和 release 元数据。'].filter(Boolean).join('\n')
      : '当前历史复盘没有可自动写入表单的推荐配置。';
  } catch (error) {
    els.artifactTitle.textContent = '历史推荐';
    els.artifactContent.textContent = `应用失败：${error.message}`;
  } finally {
    els.applyMemoryDefaults.disabled = false;
    els.applyMemoryDefaults.textContent = previousText;
  }
}

async function applyGoldDefaultsToForm() {
  els.applyGoldDefaults.disabled = true;
  const previousText = els.applyGoldDefaults.textContent;
  els.applyGoldDefaults.textContent = '应用中...';
  try {
    const result = await api('/api/gold-defaults');
    const defaults = result.defaults || {};
    const literature = defaults.literature || {};
    const execution = defaults.execution || {};
    const release = defaults.release || {};
    const supportRuns = defaults.support_runs || {};
    const applied = [];
    const notes = [];

    if (defaults.paper_grade_enabled === true) {
      const field = els.form.elements.namedItem('paper_grade_enabled');
      if (field && 'checked' in field) {
        field.checked = true;
        syncPaperGradeSecretPolicy();
        applied.push('论文级门槛=开启');
      }
    }
    if (literature.provider) {
      setFieldValue('literature_provider', literature.provider);
      applied.push(`文献模式=${literature.provider}`);
    }
    if (Array.isArray(literature.sources) && literature.sources.length) {
      setFieldValue('literature_sources', literature.sources.join(', '));
      applied.push(`sources=${literature.sources.join(', ')}`);
    }
    if (Number(literature.max_papers || 0)) {
      setNumberMinimum('max_papers', Number(literature.max_papers));
      applied.push(`max_papers>=${literature.max_papers}`);
    }
    if (Number(literature.max_search_queries || 0)) {
      setNumberMinimum('max_search_queries', Number(literature.max_search_queries));
      applied.push(`max_search_queries>=${literature.max_search_queries}`);
    }
    const seedPapers = Array.isArray(literature.seed_papers) ? literature.seed_papers : [];
    if (seedPapers.length) {
      const added = appendTextareaLines('seed_papers', seedPapers);
      if (added.length) applied.push(`Seed papers+${added.length}`);
    }
    const fulltextPaths = Array.isArray(literature.fulltext_paths) ? literature.fulltext_paths : [];
    if (fulltextPaths.length) {
      const added = appendTextareaLines('fulltext_paths', fulltextPaths);
      if (added.length) applied.push(`全文路径+${added.length}`);
    }
    const extraQueries = Array.isArray(literature.extra_search_queries) ? literature.extra_search_queries : [];
    if (extraQueries.length) {
      const added = appendTextareaLines('extra_search_queries', extraQueries);
      if (added.length) applied.push(`补充检索式+${added.length}`);
    }
    if (execution.mode) {
      setFieldValue('execution_mode', execution.mode);
      applied.push(`执行模式=${execution.mode}`);
    }
    if (Array.isArray(execution.allowed_commands)) {
      for (const command of execution.allowed_commands) ensureCommaListValue('allowed_commands', command);
      if (execution.allowed_commands.length) applied.push(`命令白名单+${execution.allowed_commands.length}`);
    }
    if (Number(execution.repeats || 0)) {
      setNumberMinimum('execution_repeats', Number(execution.repeats));
      applied.push(`重复次数>=${execution.repeats}`);
    }
    if (Number(execution.timeout_seconds || 0)) {
      setNumberMinimum('timeout_seconds', Number(execution.timeout_seconds));
      applied.push(`超时秒数>=${execution.timeout_seconds}`);
    }
    if (supportRuns.benchmark_pack_run_dir) {
      setFieldValue('benchmark_pack_run_dir', supportRuns.benchmark_pack_run_dir);
      applied.push(`Benchmark pack run=${supportRuns.benchmark_pack_run_dir}`);
    }
    if (supportRuns.fulltext_grounding_run_dir) {
      setFieldValue('fulltext_grounding_run_dir', supportRuns.fulltext_grounding_run_dir);
      applied.push(`Fulltext grounding run=${supportRuns.fulltext_grounding_run_dir}`);
    }
    const manifestPaths = Array.isArray(execution.benchmark_manifest_paths) ? execution.benchmark_manifest_paths : [];
    const existingManifestCount = textareaLines('benchmark_manifests').length;
    if (manifestPaths.length >= 3 && existingManifestCount < 3) {
      const added = appendTextareaLines('benchmark_manifests', manifestPaths);
      if (added.length) applied.push(`正式 Benchmark Manifest+${added.length}`);
    } else if (manifestPaths.length >= 3) {
      notes.push('当前已有 3 条以上 Benchmark Manifest，未覆盖；请确认它们真的是 candidate/baseline/ablation 三角色公开外部 benchmark。');
    } else {
      notes.push('未发现可自动回填的正式外部三角色 benchmark pack；请在 benchmarks/<domain>/ 下补 candidate/baseline/ablation manifest。');
    }

    const minSeeds = Number(literature.min_doi_url_seed_papers || literature.min_seed_papers || 3);
    if (seedPapers.length < minSeeds) {
      notes.push(`仍需人工填写至少 ${minSeeds} 条真实 DOI/URL seed papers；不要使用占位 DOI。`);
    } else {
      notes.push(`已回填 ${seedPapers.length} 条 UCI Iris DOI/URL seed papers；启动前仍需人工核对题名、年份、URL/DOI 和相关性。`);
    }
    const releaseValues = releaseConfigValues(release);
    for (const [key, value] of releaseValues) {
      setFieldValue(releaseFormFieldByConfigKey[key], value);
    }
    if (releaseValues.length) {
      applied.push(`Release 元数据+${releaseValues.length}`);
    }
    const missingRelease = missingReleaseFormFields(release.required_fields);
    if (missingRelease.length) {
      notes.push(`Release 必填仍需人工填写：${missingRelease.map(releaseFieldLabel).join('、')}。`);
    }
    if (Array.isArray(defaults.manual_todos)) {
      notes.push(...defaults.manual_todos.map((item) => String(item || '').trim()).filter(Boolean));
    }

    els.artifactTitle.textContent = 'Gold defaults 已应用';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      '已写入左侧表单：',
      ...applied.map((item) => `- ${item}`),
      '',
      '仍需人工完成：',
      ...[...new Set(notes)].map((item) => `- ${item}`),
      '',
      '这只更新表单配置，不会启动研究、批准 review gate 或执行 gate；启动前请依次运行 Env LLM、预检配置、预览文献、校验 Benchmark 和 Gold Doctor。',
    ].filter(Boolean).join('\n');
    updateActionButtons();
  } catch (error) {
    els.artifactTitle.textContent = 'Gold defaults';
    els.artifactContent.textContent = `应用失败：${error.message}`;
  } finally {
    els.applyGoldDefaults.disabled = false;
    els.applyGoldDefaults.textContent = previousText;
  }
}

async function runGoldDefaultsSmoke() {
  els.goldDefaultsSmoke.disabled = true;
  const previousText = els.goldDefaultsSmoke.textContent;
  els.goldDefaultsSmoke.textContent = '烟测中...';
  clearGoldLaunchCommands();
  try {
    const topic = String(els.form.elements.namedItem('topic')?.value || '').trim() || 'Iris classification benchmark smoke';
    const result = await api('/api/gold-defaults-smoke', {
      method: 'POST',
      body: JSON.stringify({topic}),
    });
    const status = result.report?.status || 'unknown';
    const focus = safeLaunchText(result.report?.prelaunch_focus?.category);
    const serverEnv = result.report?.server_environment || {};
    const envTotal = Number(serverEnv.required_total || 0);
    const envPresent = Number(serverEnv.required_present || 0);
    const gatewayStatus = safeLaunchText(serverEnv.gateway_socket?.status || '');
    const suffixParts = [];
    if (focus) suffixParts.push(`focus: ${focus}`);
    if (envTotal) suffixParts.push(`env: ${envPresent}/${envTotal}`);
    if (gatewayStatus) suffixParts.push(`gateway: ${gatewayStatus}`);
    els.artifactTitle.textContent = `gold defaults smoke: ${status}${suffixParts.length ? ` / ${suffixParts.join(' / ')}` : ''}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      goldEnvironmentActionMarkdown(result.report),
      result.markdown || JSON.stringify(result.report || result, null, 2),
    ].filter(Boolean).join('\n\n');
    renderGoldLaunchChecklist(result.report?.components);
    renderGoldLaunchCommands(Object.values(result.report?.safe_commands || {}).filter(Boolean));
  } catch (error) {
    els.artifactTitle.textContent = 'gold defaults smoke';
    els.artifactContent.textContent = `Gold Defaults Smoke 失败：${error.message}`;
    clearGoldLaunchCommands();
  } finally {
    els.goldDefaultsSmoke.disabled = false;
    els.goldDefaultsSmoke.textContent = previousText;
  }
}

async function loadRunLibrary() {
  const query = String(els.libraryQuery.value || '').trim() || String(els.form.elements.namedItem('topic')?.value || '').trim();
  els.librarySearch.disabled = true;
  const previousText = els.librarySearch.textContent;
  els.librarySearch.textContent = '检索中';
  try {
    const result = await api(`/api/library?q=${encodeURIComponent(query)}`);
    els.artifactTitle.textContent = query ? `runs-library: ${query}` : 'runs-library';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.library || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'runs-library';
    els.artifactContent.textContent = `成果库检索失败：${error.message}`;
  } finally {
    els.librarySearch.disabled = false;
    els.librarySearch.textContent = previousText;
  }
}

async function approveCurrentRun() {
  if (!canApprove(state.currentRun)) return;
  const runId = state.currentRun.id;
  const payload = payloadForCurrentRunAction();
  if (approvalNotesRequired(state.currentRun) && payload.review_notes.length < 8) {
    const gateDetails = literatureQualityGateDetails(state.currentRun);
    const retrievalDetails = literatureRetrievalGateDetails(state.currentRun);
    const evidenceDetails = literatureEvidenceContractDetails(state.currentRun);
    const ideaGateDetails = ideaExperimentGateDetails(state.currentRun);
    els.artifactContent.textContent = state.currentRun.stage === 'awaiting_execution_approval'
      ? ['批准失败：local/benchmark 执行前必须在“审核意见”填写命令计划和安全审计确认说明。', ideaGateDetails].filter(Boolean).join('\n\n')
      : ['批准失败：当前 review gate 不是 pass，请在“审核意见”填写人工判断、修复说明或风险接受理由。', retrievalDetails, evidenceDetails, gateDetails].filter(Boolean).join('\n\n');
    return;
  }
  state.approvingRunId = runId;
  updateActionButtons();
  try {
    const result = await api(`/api/runs/${encodeURIComponent(runId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (result.run) setCurrentRun(result.run);
    await refreshRuns(true);
    startPolling();
  } catch (error) {
    els.artifactContent.textContent = `批准失败：${error.message}`;
  } finally {
    state.approvingRunId = null;
    updateActionButtons();
  }
}

async function requestRevisionCurrentRun() {
  if (!canRequestRevision(state.currentRun)) return;
  const runId = state.currentRun.id;
  state.revisionRunId = runId;
  updateActionButtons();
  try {
    const result = await api(`/api/runs/${encodeURIComponent(runId)}/revision`, {
      method: 'POST',
      body: JSON.stringify(payloadForCurrentRunAction({notesOnly: true})),
    });
    if (result.run) setCurrentRun(result.run);
    await refreshRuns(true);
    startPolling();
  } catch (error) {
    els.artifactContent.textContent = `退回失败：${error.message}`;
  } finally {
    state.revisionRunId = null;
    updateActionButtons();
  }
}

async function cancelCurrentRun() {
  if (!canCancel(state.currentRun)) return;
  const runId = state.currentRun.id;
  state.cancellingRunId = runId;
  updateActionButtons();
  try {
    const result = await api(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({reason: 'user_requested'}),
    });
    if (result.run) setCurrentRun(result.run);
    await refreshRuns(true);
    startPolling();
  } catch (error) {
    els.artifactContent.textContent = `取消失败：${error.message}`;
  } finally {
    state.cancellingRunId = null;
    updateActionButtons();
  }
}

async function runPreflight() {
  els.preflight.disabled = true;
  const previousText = els.preflight.textContent;
  els.preflight.textContent = '预检中...';
  try {
    const payload = payloadForRunAction();
    payload.ping_llm = true;
    const result = await api('/api/preflight', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    els.artifactTitle.textContent = 'preflight';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'preflight';
    els.artifactContent.textContent = `预检失败：${error.message}`;
  } finally {
    els.preflight.disabled = false;
    els.preflight.textContent = previousText;
  }
}

async function runEnvLlmPreflight() {
  els.envLlmPreflight.disabled = true;
  const previousText = els.envLlmPreflight.textContent;
  els.envLlmPreflight.textContent = '检查中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    payload.ping_llm = true;
    const result = await api('/api/env-llm-preflight', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.env_llm?.status || result.report?.status || 'unknown';
    const ping = result.env_llm?.ping_status ? ` / ping: ${result.env_llm.ping_status}` : '';
    els.artifactTitle.textContent = `env llm preflight: ${status}${ping}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.env_llm || result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'env llm preflight';
    els.artifactContent.textContent = `Env LLM 检查失败：${error.message}`;
  } finally {
    els.envLlmPreflight.disabled = false;
    els.envLlmPreflight.textContent = previousText;
  }
}

async function lintGoldEnv() {
  els.goldEnvLint.disabled = true;
  const previousText = els.goldEnvLint.textContent;
  els.goldEnvLint.textContent = '检查中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const result = await api('/api/gold-env-lint', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const missing = Array.isArray(result.report?.missing_required_fields) ? result.report.missing_required_fields.length : 0;
    const invalid = Array.isArray(result.report?.invalid_required_fields) ? result.report.invalid_required_fields.length : 0;
    const suffix = missing || invalid ? ` / missing: ${missing} / invalid: ${invalid}` : '';
    els.artifactTitle.textContent = `gold env: ${status}${suffix}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'gold env';
    els.artifactContent.textContent = `Gold Env 检查失败：${error.message}`;
  } finally {
    els.goldEnvLint.disabled = false;
    els.goldEnvLint.textContent = previousText;
  }
}

async function showGoldEnvLaunchKit() {
  els.goldEnvLaunchKit.disabled = true;
  const previousText = els.goldEnvLaunchKit.textContent;
  els.goldEnvLaunchKit.textContent = '生成中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const result = await api('/api/gold-env-launch-kit', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const ignored = Array.isArray(result.report?.ignored_payload_secret_fields) ? result.report.ignored_payload_secret_fields.length : 0;
    const serverEnv = result.report?.server_environment || {};
    const envTotal = Number(serverEnv.required_total || 0);
    const envPresent = Number(serverEnv.required_present || 0);
    const gatewayStatus = safeLaunchText(serverEnv.gateway_socket?.status || '');
    const suffixParts = [];
    if (envTotal) suffixParts.push(`env: ${envPresent}/${envTotal}`);
    if (gatewayStatus) suffixParts.push(`gateway: ${gatewayStatus}`);
    if (ignored) suffixParts.push(`ignored secrets: ${ignored}`);
    els.artifactTitle.textContent = `gold env kit: ${status}${suffixParts.length ? ` / ${suffixParts.join(' / ')}` : ''}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      goldEnvironmentActionMarkdown(result.report),
      result.markdown || JSON.stringify(result.report || result, null, 2),
    ].filter(Boolean).join('\n\n');
  } catch (error) {
    els.artifactTitle.textContent = 'gold env kit';
    els.artifactContent.textContent = `Gold Env Kit 生成失败：${error.message}`;
  } finally {
    els.goldEnvLaunchKit.disabled = false;
    els.goldEnvLaunchKit.textContent = previousText;
  }
}

async function runGoldLaunchBundle() {
  els.goldLaunchBundle.disabled = true;
  const previousText = els.goldLaunchBundle.textContent;
  els.goldLaunchBundle.textContent = '检查中...';
  clearGoldLaunchCommands();
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    if (state.currentRun?.id) payload.candidate_run_id = state.currentRun.id;
    const result = await api('/api/gold-launch-bundle', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const counts = result.report?.component_status_counts || {};
    const blocks = Number(counts.block || 0);
    const reviews = Number(counts.review || 0);
    const focus = safeLaunchText(result.report?.prelaunch_focus?.category);
    const suffix = [blocks || reviews ? `blocks: ${blocks} / review: ${reviews}` : '', focus ? `focus: ${focus}` : ''].filter(Boolean).join(' / ');
    els.artifactTitle.textContent = `gold bundle: ${status}${suffix ? ` / ${suffix}` : ''}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      goldEnvironmentActionMarkdown(result.report),
      result.markdown || JSON.stringify(result.report || result, null, 2),
    ].filter(Boolean).join('\n\n');
    renderGoldLaunchChecklist(result.report?.components);
  } catch (error) {
    els.artifactTitle.textContent = 'gold bundle';
    els.artifactContent.textContent = `Gold Bundle 检查失败：${error.message}`;
    clearGoldLaunchCommands();
  } finally {
    els.goldLaunchBundle.disabled = false;
    els.goldLaunchBundle.textContent = previousText;
  }
}

async function runGoldLaunch() {
  els.goldRunLaunch.disabled = true;
  const previousText = els.goldRunLaunch.textContent;
  els.goldRunLaunch.textContent = '启动检查中...';
  clearGoldLaunchCommands();
  try {
    const payload = payloadFromForm();
    payload.paper_grade_enabled = true;
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const response = await fetch('/api/gold-run-launch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      const status = result.report?.status || 'blocked';
      const focus = safeLaunchText(result.report?.prelaunch_focus?.category);
      const serverEnv = result.report?.reports?.gold_env?.server_environment || {};
      const envTotal = Number(serverEnv.required_total || 0);
      const envPresent = Number(serverEnv.required_present || 0);
      const gatewayStatus = safeLaunchText(serverEnv.gateway_socket?.status || '');
      const suffixParts = [];
      if (focus) suffixParts.push(`focus: ${focus}`);
      if (envTotal) suffixParts.push(`env: ${envPresent}/${envTotal}`);
      if (gatewayStatus) suffixParts.push(`gateway: ${gatewayStatus}`);
      els.artifactTitle.textContent = `gold launch: ${status}${suffixParts.length ? ` / ${suffixParts.join(' / ')}` : ''}`;
      els.downloadLink.href = '#';
      els.artifactContent.textContent = [
        goldEnvironmentActionMarkdown(result.report),
        result.markdown || result.error || `Gold Launch 失败：HTTP ${response.status}`,
      ].filter(Boolean).join('\n\n');
      renderGoldLaunchChecklist(result.report?.components);
      renderGoldLaunchCommands(result.report?.launch_plan?.safe_commands);
      return;
    }
    setCurrentRun(result.run);
    await refreshRuns(true);
    await loadArtifact(state.selectedFile);
    startPolling();
    const status = result.launch_bundle?.status || 'ready_to_start';
    els.artifactTitle.textContent = `gold launch: ${status}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.launch_bundle || result, null, 2);
    renderGoldLaunchChecklist(result.launch_bundle?.components);
    renderGoldLaunchCommands(result.post_launch_guidance?.commands || result.launch_bundle?.launch_plan?.safe_commands);
  } catch (error) {
    els.artifactTitle.textContent = 'gold launch';
    els.artifactContent.textContent = `Gold Launch 失败：${error.message}`;
    clearGoldLaunchCommands();
  } finally {
    els.goldRunLaunch.disabled = false;
    els.goldRunLaunch.textContent = previousText;
  }
}

async function runGoldDoctor() {
  els.goldRunDoctor.disabled = true;
  const previousText = els.goldRunDoctor.textContent;
  els.goldRunDoctor.textContent = '检查中...';
  clearGoldLaunchCommands();
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    payload.ping_llm = false;
    if (state.currentRun?.id) payload.candidate_run_id = state.currentRun.id;
    const result = await api('/api/gold-run-doctor', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const launch = result.launch_manifest?.status ? ` / launch: ${result.launch_manifest.status}` : '';
    const readiness = publicGoldLaunchReadiness(result.launch_manifest?.launch_readiness || result.report?.launch_readiness);
    const blocking = readiness.blocking_items.length ? ` / blocks: ${readiness.blocking_items.length}` : '';
    const review = readiness.review_items.length ? ` / review: ${readiness.review_items.length}` : '';
    els.artifactTitle.textContent = `gold doctor: ${status}${launch}${blocking}${review}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || result.launch_markdown || JSON.stringify(result.report || result, null, 2);
    renderGoldLaunchChecklist(result.launch_manifest?.launch_checklist);
    renderGoldLaunchCommands(result.launch_commands);
  } catch (error) {
    els.artifactTitle.textContent = 'gold doctor';
    els.artifactContent.textContent = `Gold Doctor 检查失败：${error.message}`;
    clearGoldLaunchCommands();
  } finally {
    els.goldRunDoctor.disabled = false;
    els.goldRunDoctor.textContent = previousText;
  }
}

async function runGoldVerify() {
  if (!state.currentRun?.id) {
    els.artifactTitle.textContent = 'gold verify';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = '请先选择一个已完成或已有产物的 run。';
    return;
  }
  els.goldRunVerify.disabled = true;
  const previousText = els.goldRunVerify.textContent;
  els.goldRunVerify.textContent = '验证中...';
  clearGoldLaunchCommands();
  try {
    const result = await api('/api/gold-run-verify', {
      method: 'POST',
      body: JSON.stringify({candidate_run_id: state.currentRun.id}),
    });
    const status = result.report?.status || 'unknown';
    const missing = Number(result.report?.missing_artifact_count || 0);
    const repairs = Number(result.report?.repair_plan_items || 0);
    const suffix = missing || repairs ? ` / missing: ${missing} / repairs: ${repairs}` : '';
    els.artifactTitle.textContent = `gold verify: ${status}${suffix}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [result.markdown || JSON.stringify(result.report || result, null, 2), goldVerifyFollowupLines(result)].filter(Boolean).join('\n\n');
    await refreshRuns(true);
  } catch (error) {
    els.artifactTitle.textContent = 'gold verify';
    els.artifactContent.textContent = `Gold Verify 失败：${error.message}`;
  } finally {
    els.goldRunVerify.textContent = previousText;
    updateActionButtons();
  }
}

async function previewLiterature() {
  els.literaturePreview.disabled = true;
  const previousText = els.literaturePreview.textContent;
  els.literaturePreview.textContent = '预览中...';
  try {
    const result = await api('/api/literature-preview', {
      method: 'POST',
      body: JSON.stringify(payloadFromForm()),
    });
    state.literaturePreviewReport = result.report || null;
    const status = result.report?.status || 'unknown';
    els.artifactTitle.textContent = `literature preview: ${status}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
    updateActionButtons();
  } catch (error) {
    state.literaturePreviewReport = null;
    els.artifactTitle.textContent = 'literature preview';
    els.artifactContent.textContent = `文献预览失败：${error.message}`;
    updateActionButtons();
  } finally {
    els.literaturePreview.disabled = false;
    els.literaturePreview.textContent = previousText;
  }
}

async function runPaperGradeProbe() {
  els.paperGradeProbe.disabled = true;
  const previousText = els.paperGradeProbe.textContent;
  els.paperGradeProbe.textContent = 'Probe中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const result = await api('/api/paper-grade-probe', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const sources = result.report?.source_summary?.successful_sources;
    const seeds = result.report?.seed_summary?.metadata_resolved_seed_papers;
    const suffix = Number.isFinite(Number(sources)) && Number.isFinite(Number(seeds))
      ? ` / sources: ${sources} / seeds: ${seeds}`
      : '';
    els.artifactTitle.textContent = `paper-grade probe: ${status}${suffix}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'paper-grade probe';
    els.artifactContent.textContent = `Gold 文献 Probe 失败：${error.message}`;
  } finally {
    els.paperGradeProbe.disabled = false;
    els.paperGradeProbe.textContent = previousText;
  }
}

function applyLiteraturePreviewSeedsToForm() {
  if (!canApplyLiteraturePreviewSeeds()) {
    els.artifactTitle.textContent = '文献预览 Seed';
    els.artifactContent.textContent = '没有可回填的当前课题预览 Seed。请先点击“预览文献”，人工核对候选 DOI/URL 后再回填。';
    return;
  }
  const entries = state.literaturePreviewReport.recommended_seed_entries || [];
  const added = appendTextareaLines('seed_papers', entries);
  const seedRole = state.literaturePreviewReport.seed_role_coverage || {};
  const roleCounts = seedRole.role_counts || {};
  const roleSummary = ['review', 'benchmark_dataset', 'baseline_method', 'recent']
    .map((role) => `${role}=${Number(roleCounts[role] || 0)}`)
    .join(', ');
  const missingRoles = Array.isArray(seedRole.missing_roles) && seedRole.missing_roles.length
    ? `缺失角色：${seedRole.missing_roles.join(', ')}`
    : '缺失角色：无';
  els.artifactTitle.textContent = '预览 Seed 已应用';
  els.downloadLink.href = '#';
  els.artifactContent.textContent = added.length
    ? ['已写入人工种子文献：', ...added.map((item) => `- ${item}`), '', `预览 Seed 角色覆盖：${seedRole.status || '-'}；${roleSummary}`, missingRoles, '', '这只更新 seed_papers 表单，不会启动研究、批准 review gate 或进入 idea/实验；启动前仍需人工核对题名、年份、DOI/URL 和相关性。'].join('\n')
    : '预览 Seed 已存在于人工种子文献，未重复写入。';
}

async function previewBenchmark() {
  els.benchmarkPreview.disabled = true;
  const previousText = els.benchmarkPreview.textContent;
  els.benchmarkPreview.textContent = '校验中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const result = await api('/api/benchmark-preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    els.artifactTitle.textContent = `benchmark preview: ${status}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'benchmark preview';
    els.artifactContent.textContent = `Benchmark 校验失败：${error.message}`;
  } finally {
    els.benchmarkPreview.disabled = false;
    els.benchmarkPreview.textContent = previousText;
  }
}

async function showBenchmarkTemplate() {
  els.benchmarkTemplate.disabled = true;
  const previousText = els.benchmarkTemplate.textContent;
  els.benchmarkTemplate.textContent = '生成中...';
  try {
    const topic = payloadFromForm().topic;
    const result = await api(`/api/benchmark-template?topic=${encodeURIComponent(topic)}`);
    const template = result.template || {};
    const command = Array.isArray(template.command) ? template.command : [];
    setFieldValue('execution_mode', 'benchmark');
    if (command.length) ensureCommaListValue('allowed_commands', String(command[0]));
    els.benchmarkManifestDraftPath.value = result.suggested_path || '';
    els.benchmarkManifestDraft.value = JSON.stringify(template, null, 2);
    els.artifactTitle.textContent = 'Benchmark Manifest 模板';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || '',
      '',
      '```json',
      JSON.stringify(template, null, 2),
      '```',
    ].join('\n');
  } catch (error) {
    els.artifactTitle.textContent = 'benchmark template';
    els.artifactContent.textContent = `生成模板失败：${error.message}`;
  } finally {
    els.benchmarkTemplate.disabled = false;
    els.benchmarkTemplate.textContent = previousText;
  }
}

function benchmarkManifestDraftPayload() {
  return {
    path: String(els.benchmarkManifestDraftPath.value || '').trim(),
    manifest: String(els.benchmarkManifestDraft.value || '').trim(),
    allowed_commands: String(payloadFromForm().allowed_commands || 'python3, pytest'),
  };
}

async function lintBenchmarkManifestDraft() {
  els.benchmarkManifestLint.disabled = true;
  const previousText = els.benchmarkManifestLint.textContent;
  els.benchmarkManifestLint.textContent = '校验中...';
  try {
    const result = await api('/api/benchmark-manifest-lint', {
      method: 'POST',
      body: JSON.stringify(benchmarkManifestDraftPayload()),
    });
    const status = result.report?.status || 'unknown';
    els.artifactTitle.textContent = `Manifest 草稿校验：${status}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'Manifest 草稿校验';
    els.artifactContent.textContent = `校验失败：${error.message}`;
  } finally {
    els.benchmarkManifestLint.disabled = false;
    els.benchmarkManifestLint.textContent = previousText;
  }
}

async function saveBenchmarkManifestDraft() {
  els.benchmarkManifestSave.disabled = true;
  const previousText = els.benchmarkManifestSave.textContent;
  els.benchmarkManifestSave.textContent = '保存中...';
  try {
    const result = await api('/api/benchmark-manifest-save', {
      method: 'POST',
      body: JSON.stringify(benchmarkManifestDraftPayload()),
    });
    if (result.path) appendTextareaLines('benchmark_manifests', [result.path]);
    setFieldValue('execution_mode', 'benchmark');
    els.artifactTitle.textContent = 'Manifest 草稿已保存';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      result.markdown || '',
      '',
      result.path ? `已写入 Benchmark Manifest：${result.path}` : '',
      '下一步先点击“校验 Benchmark”；保存不会创建 run 或执行命令。',
    ].filter(Boolean).join('\n');
  } catch (error) {
    els.artifactTitle.textContent = 'Manifest 草稿保存';
    els.artifactContent.textContent = `保存失败：${error.message}`;
  } finally {
    els.benchmarkManifestSave.disabled = false;
    els.benchmarkManifestSave.textContent = previousText;
  }
}

async function lintReleaseMetadata() {
  els.releaseMetadataLint.disabled = true;
  const previousText = els.releaseMetadataLint.textContent;
  els.releaseMetadataLint.textContent = '校验中...';
  try {
    const payload = payloadFromForm();
    delete payload.llm_api_key;
    delete payload.semantic_scholar_api_key;
    delete payload.openalex_api_key;
    const result = await api('/api/release-metadata-lint', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const status = result.report?.status || 'unknown';
    const blocked = Array.isArray(result.report?.blocking_fields) && result.report.blocking_fields.length
      ? ` / blocked: ${result.report.blocking_fields.join(', ')}`
      : '';
    els.artifactTitle.textContent = `release metadata: ${status}${blocked}`;
    els.downloadLink.href = '#';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.report || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = 'release metadata lint';
    els.artifactContent.textContent = `Release 校验失败：${error.message}`;
  } finally {
    els.releaseMetadataLint.disabled = false;
    els.releaseMetadataLint.textContent = previousText;
  }
}

async function applyBenchmarkExampleToForm() {
  els.benchmarkExample.disabled = true;
  const previousText = els.benchmarkExample.textContent;
  els.benchmarkExample.textContent = '填入中...';
  try {
    const result = await api('/api/benchmark-examples');
    const example = Array.isArray(result.examples) ? result.examples[0] : null;
    if (!example?.path) {
      els.artifactTitle.textContent = 'benchmark examples';
      els.artifactContent.textContent = '没有找到 examples/**/manifest.json。';
      return;
    }
    setFieldValue('execution_mode', 'benchmark');
    setFieldValue('benchmark_manifests', example.path);
    const executable = Array.isArray(example.command) && example.command.length ? String(example.command[0]) : '';
    if (executable) ensureCommaListValue('allowed_commands', executable);
    els.artifactTitle.textContent = 'Benchmark 示例已填入';
    els.downloadLink.href = '#';
    els.artifactContent.textContent = [
      `已填入：${example.name || example.path}`,
      `manifest: ${example.path}`,
      `command: ${(example.command || []).join(' ') || '-'}`,
      `metrics: ${example.metrics_path || '-'}`,
      `dataset: ${example.dataset_url || example.benchmark_url || '-'}`,
      `license: ${example.license || '-'}`,
      `baseline: ${example.baseline || '-'} ${example.baseline_version || ''}`.trim(),
      `citation: ${example.citation || '-'}`,
      '',
      '正在运行只读 preview；不会创建 run 或执行命令。',
    ].join('\n');
    await previewBenchmark();
  } catch (error) {
    els.artifactTitle.textContent = 'benchmark examples';
    els.artifactContent.textContent = `填入示例失败：${error.message}`;
  } finally {
    els.benchmarkExample.disabled = false;
    els.benchmarkExample.textContent = previousText;
  }
}

async function resumeCurrentRun() {
  if (!canResume(state.currentRun)) return;
  const runId = state.currentRun.id;
  const endpoint = canRepairResume(state.currentRun) ? 'repair-resume' : 'resume';
  state.resumingRunId = runId;
  updateActionButtons();
  try {
    const result = await api(`/api/runs/${encodeURIComponent(runId)}/${endpoint}`, {
      method: 'POST',
      body: JSON.stringify(payloadForCurrentRunAction()),
    });
    if (result.run) setCurrentRun(result.run);
    await refreshRuns(true);
    startPolling();
  } catch (error) {
    els.artifactContent.textContent = `恢复失败：${error.message}`;
  } finally {
    state.resumingRunId = null;
    updateActionButtons();
  }
}

async function previewRepairResumeCurrentRun() {
  if (!canRepairResume(state.currentRun)) return;
  const runId = state.currentRun.id;
  state.repairPreviewRunId = runId;
  updateActionButtons();
  try {
    const result = await api(`/api/runs/${encodeURIComponent(runId)}/repair-resume-preview`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    state.repairPreviewPlan = {run_id: runId, plan: result.plan || {}, markdown: result.markdown || ''};
    state.selectedFile = '12-repair-resume-plan.md';
    if (result.run) setCurrentRun(result.run);
    await refreshRuns(true);
    els.artifactTitle.textContent = '修复恢复预览';
    els.downloadLink.href = `/api/runs/${encodeURIComponent(runId)}/artifact?file=12-repair-resume-plan.md`;
    els.downloadLink.download = '12-repair-resume-plan.md';
    els.artifactContent.textContent = result.markdown || JSON.stringify(result.plan || result, null, 2);
  } catch (error) {
    els.artifactTitle.textContent = '修复恢复预览';
    els.artifactContent.textContent = `预览失败：${error.message}`;
  } finally {
    state.repairPreviewRunId = null;
    updateActionButtons();
  }
}

function applyRepairResumePreviewToForm() {
  if (!canApplyRepairResumePreview(state.currentRun)) return;
  const plan = state.repairPreviewPlan.plan || state.repairPreviewPlan;
  const literature = plan.recommended_config || {};
  const execution = plan.recommended_execution_config || {};
  const paperGrade = plan.recommended_paper_grade_config || {};
  const release = plan.recommended_release_config || {};
  const applied = [];

  if (literature.literature_provider) {
    setFieldValue('literature_provider', literature.literature_provider);
    applied.push(`文献模式=${literature.literature_provider}`);
  }
  if (Array.isArray(literature.sources) && literature.sources.length) {
    setFieldValue('literature_sources', literature.sources.join(', '));
    applied.push(`sources=${literature.sources.join(', ')}`);
  }
  if (Number(literature.max_papers || 0)) {
    setNumberMinimum('max_papers', Number(literature.max_papers));
    applied.push(`max_papers>=${literature.max_papers}`);
  }
  if (Number(literature.max_search_queries || 0)) {
    setNumberMinimum('max_search_queries', Number(literature.max_search_queries));
    applied.push(`max_search_queries>=${literature.max_search_queries}`);
  }
  if (execution.execution_mode) {
    setFieldValue('execution_mode', execution.execution_mode);
    applied.push(`执行模式=${execution.execution_mode}`);
  }
  if (Array.isArray(execution.allowed_commands) && execution.allowed_commands.length) {
    for (const command of execution.allowed_commands) ensureCommaListValue('allowed_commands', command);
    applied.push(`命令白名单+${execution.allowed_commands.length}`);
  }
  if (Number(execution.execution_repeats || 0)) {
    setNumberMinimum('execution_repeats', Number(execution.execution_repeats));
    applied.push(`重复次数>=${execution.execution_repeats}`);
  }
  if (Number(execution.timeout_seconds || 0)) {
    setNumberMinimum('timeout_seconds', Number(execution.timeout_seconds));
    applied.push(`超时秒数>=${execution.timeout_seconds}`);
  }
  if (Array.isArray(execution.benchmark_manifest_paths) && execution.benchmark_manifest_paths.length) {
    const added = appendTextareaLines('benchmark_manifests', execution.benchmark_manifest_paths);
    if (added.length) applied.push(`Benchmark Manifest+${added.length}`);
  }
  if (paperGrade.enabled === true) {
    const field = els.form.elements.namedItem('paper_grade_enabled');
    if (field && 'checked' in field) {
      field.checked = true;
      syncPaperGradeSecretPolicy();
      applied.push('论文级门槛=开启');
    }
  }
  const releaseValues = releaseConfigValues(release);
  for (const [key, value] of releaseValues) {
    setFieldValue(releaseFormFieldByConfigKey[key], value);
  }
  if (releaseValues.length) {
    applied.push(`Release 元数据+${releaseValues.length}`);
  }

  els.artifactTitle.textContent = '修复建议已应用';
  els.downloadLink.href = '#';
  els.artifactContent.textContent = applied.length
    ? ['已写入左侧表单：', ...applied.map((item) => `- ${item}`), '', '这只更新表单配置，不会批准 review gate 或执行 gate；启动修复恢复前请重新预检配置，并人工核对 seed、query、manifest、白名单和审核意见。'].join('\n')
    : '当前修复预览没有可自动写入表单的配置建议。';
  updateActionButtons();
}

function applyLiteratureFeedbackToForm() {
  if (!canApplyLiteratureFeedback(state.currentRun)) return;
  const feedback = state.currentRun.literature_search_feedback || {};
  const rescue = state.currentRun.literature_rescue_plan || {};
  const execution = state.currentRun.literature_rescue_execution || {};
  const seed = state.currentRun.seed_intake || {};
  const config = feedback.next_run_config || {};
  const applied = [];
  if (config.literature_provider) {
    setFieldValue('literature_provider', config.literature_provider);
    applied.push(`文献模式=${config.literature_provider}`);
  }
  if (Array.isArray(config.sources) && config.sources.length) {
    setFieldValue('literature_sources', config.sources.join(', '));
    applied.push(`sources=${config.sources.join(', ')}`);
  }
  if (Number(config.max_papers || 0)) {
    setNumberMinimum('max_papers', Number(config.max_papers));
    applied.push(`max_papers>=${config.max_papers}`);
  }
  if (Number(config.max_search_queries || 0)) {
    setNumberMinimum('max_search_queries', Number(config.max_search_queries));
    applied.push(`max_search_queries>=${config.max_search_queries}`);
  }
  if (Array.isArray(feedback.top_queries) && feedback.top_queries.length) {
    const added = appendTextareaLines('extra_search_queries', feedback.top_queries);
    if (added.length) applied.push(`补充检索式+${added.length}`);
  }
  if (Array.isArray(rescue.role_queries) && rescue.role_queries.length) {
    setFieldValue('literature_provider', 'online');
    setNumberMinimum('max_papers', 12);
    setNumberMinimum('max_search_queries', 6);
    const added = appendTextareaLines('extra_search_queries', rescue.role_queries);
    applied.push('文献模式=online');
    applied.push('max_papers>=12');
    applied.push('max_search_queries>=6');
    if (added.length) applied.push(`证据角色补检索 query+${added.length}`);
  } else if (Array.isArray(rescue.top_queries) && rescue.top_queries.length) {
    const added = appendTextareaLines('extra_search_queries', rescue.top_queries);
    if (added.length) applied.push(`补检索计划 query+${added.length}`);
  }
  if (Array.isArray(execution.unresolved_queries) && execution.unresolved_queries.length) {
    const added = appendTextareaLines('extra_search_queries', execution.unresolved_queries);
    if (added.length) applied.push(`未闭环补检索 query+${added.length}`);
  }
  if (Array.isArray(seed.role_repair_queries) && seed.role_repair_queries.length) {
    setFieldValue('literature_provider', 'online');
    setNumberMinimum('max_papers', 12);
    setNumberMinimum('max_search_queries', 6);
    const added = appendTextareaLines('extra_search_queries', seed.role_repair_queries);
    applied.push('文献模式=online');
    applied.push('max_papers>=12');
    applied.push('max_search_queries>=6');
    if (added.length) applied.push(`Seed 角色补检索 query+${added.length}`);
  }
  if (Array.isArray(seed.suggested_seed_entries) && seed.suggested_seed_entries.length) {
    const added = appendTextareaLines('seed_papers', seed.suggested_seed_entries);
    if (added.length) applied.push(`人工种子文献+${added.length}`);
  }
  els.artifactTitle.textContent = '检索建议已应用';
  els.downloadLink.href = '#';
  els.artifactContent.textContent = applied.length
    ? ['已写入左侧表单：', ...applied.map((item) => `- ${item}`), '', '未闭环 query 和 Seed 角色缺口需要人工核对；候选 DOI/URL 已写入人工种子文献，启动前仍需人工核对题名、年份和相关性，再预检配置、修复恢复/启动研究。'].join('\n')
    : '当前 run 没有可自动写入表单的检索建议。';
}

async function loadRun(runId) {
  switchView('view-workbench');
  const requestSequence = ++state.runLoadSequence;
  if (state.runLoadController) state.runLoadController.abort();
  const controller = new AbortController();
  state.runLoadController = controller;
  try {
    const run = await api(`/api/runs/${encodeURIComponent(runId)}`, {signal: controller.signal});
    if (requestSequence !== state.runLoadSequence || controller.signal.aborted) return;
    setCurrentRun(run);
    renderRunList();
    await loadArtifact(state.selectedFile);
  } catch (error) {
    if (error.name !== 'AbortError' && requestSequence === state.runLoadSequence) {
      els.artifactContent.textContent = `加载 Run 失败：${error.message}`;
    }
  } finally {
    if (requestSequence === state.runLoadSequence) state.runLoadController = null;
  }
}


function formatInline(str) {
  if (!str) return '';
  let res = escapeHtml(str);
  res = res.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  res = res.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  res = res.replace(/`([^`]+)`/g, '<code>$1</code>');
  res = res.replace(/\[(\d+(?:,\s*\d+)*)\]/g, '<span class="academic-badge">[$1]</span>');
  return res;
}

function renderTable(rows) {
  if (!rows || rows.length < 2) return '';
  const headerRow = rows[0];
  const dataRows = rows.slice(2);

  function splitRow(r) {
    return r.split('|').slice(1, -1).map(c => c.trim());
  }

  const headers = splitRow(headerRow);
  const ths = headers.map(h => `<th>${formatInline(h)}</th>`).join('');

  const trs = dataRows.map(r => {
    const cells = splitRow(r);
    const tds = cells.map(c => `<td>${formatInline(c)}</td>`).join('');
    return `<tr>${tds}</tr>`;
  }).join('');

  return `<div class="table-responsive"><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
}

function formatAcademicMarkdown(md, filename) {
  if (!md) return '<p class="muted">尚未生成内容。</p>';
  if (filename && filename.endsWith('.json')) {
    try {
      const parsed = JSON.parse(md);
      return `<pre><code>${escapeHtml(JSON.stringify(parsed, null, 2))}</code></pre>`;
    } catch(e) {
      return `<pre><code>${escapeHtml(md)}</code></pre>`;
    }
  }

  const lines = md.split('\n');
  let title = '';
  const processedBlocks = [];
  let inCode = false;
  let codeLang = '';
  let codeLines = [];
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith('```')) {
      if (inCode) {
        processedBlocks.push({kind: 'trusted-html', html: `<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`});
        inCode = false;
        codeLines = [];
      } else {
        if (inTable) {
          processedBlocks.push({kind: 'trusted-html', html: renderTable(tableRows)});
          inTable = false;
          tableRows = [];
        }
        inCode = true;
        codeLang = line.trim().slice(3).trim();
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      inTable = true;
      tableRows.push(line.trim());
      continue;
    } else if (inTable) {
      processedBlocks.push({kind: 'trusted-html', html: renderTable(tableRows)});
      inTable = false;
      tableRows = [];
    }

    if (line.startsWith('# ') && !title) {
      title = line.slice(2).trim();
      continue;
    }

    processedBlocks.push({kind: 'text', text: line});
  }

  if (inCode) {
    processedBlocks.push({kind: 'trusted-html', html: `<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`});
  }
  if (inTable) {
    processedBlocks.push({kind: 'trusted-html', html: renderTable(tableRows)});
  }

  let html = '';
  if (title) {
    html += `
      <div class="paper-header">
        <span class="paper-meta-badge">Preprint · Verified Artifact</span>
        <h1 class="paper-title">${escapeHtml(title)}</h1>
        <p class="paper-authors">Autonomous Research Agent Framework · Multi-Agent Deliberation & Verification</p>
      </div>
    `;
  }

  let bodyHtml = '';
  let inUl = false;
  let inOl = false;
  let inBlockquote = false;
  let bqLines = [];

  for (let j = 0; j < processedBlocks.length; j++) {
    const block = processedBlocks[j];

    if (block.kind === 'trusted-html') {
      if (inUl) { bodyHtml += '</ul>'; inUl = false; }
      if (inOl) { bodyHtml += '</ol>'; inOl = false; }
      if (inBlockquote) { bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`; inBlockquote = false; bqLines = []; }
      bodyHtml += block.html;
      continue;
    }
    const l = block.text;

    if (l.startsWith('## ')) {
      if (inUl) { bodyHtml += '</ul>'; inUl = false; }
      if (inOl) { bodyHtml += '</ol>'; inOl = false; }
      if (inBlockquote) { bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`; inBlockquote = false; bqLines = []; }
      bodyHtml += `<h2>${formatInline(l.slice(3))}</h2>`;
      continue;
    }
    if (l.startsWith('### ')) {
      if (inUl) { bodyHtml += '</ul>'; inUl = false; }
      if (inOl) { bodyHtml += '</ol>'; inOl = false; }
      if (inBlockquote) { bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`; inBlockquote = false; bqLines = []; }
      bodyHtml += `<h3>${formatInline(l.slice(4))}</h3>`;
      continue;
    }
    if (l.startsWith('#### ')) {
      if (inUl) { bodyHtml += '</ul>'; inUl = false; }
      if (inOl) { bodyHtml += '</ol>'; inOl = false; }
      if (inBlockquote) { bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`; inBlockquote = false; bqLines = []; }
      bodyHtml += `<h4>${formatInline(l.slice(5))}</h4>`;
      continue;
    }

    if (l.startsWith('> ')) {
      if (inUl) { bodyHtml += '</ul>'; inUl = false; }
      if (inOl) { bodyHtml += '</ol>'; inOl = false; }
      inBlockquote = true;
      bqLines.push(formatInline(l.slice(2)));
      continue;
    } else if (inBlockquote) {
      bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`;
      inBlockquote = false;
      bqLines = [];
    }

    if (l.trim().startsWith('- ') || l.trim().startsWith('* ')) {
      if (!inUl) { bodyHtml += '<ul>'; inUl = true; }
      bodyHtml += `<li>${formatInline(l.trim().slice(2))}</li>`;
      continue;
    } else if (inUl && !l.trim().startsWith('- ') && !l.trim().startsWith('* ')) {
      bodyHtml += '</ul>';
      inUl = false;
    }

    if (/^\d+\.\s/.test(l.trim())) {
      if (!inOl) { bodyHtml += '<ol>'; inOl = true; }
      const content = l.trim().replace(/^\d+\.\s+/, '');
      bodyHtml += `<li>${formatInline(content)}</li>`;
      continue;
    } else if (inOl) {
      bodyHtml += '</ol>';
      inOl = false;
    }

    if (!l.trim()) {
      continue;
    }

    bodyHtml += `<p>${formatInline(l)}</p>`;
  }

  if (inUl) bodyHtml += '</ul>';
  if (inOl) bodyHtml += '</ol>';
  if (inBlockquote) bodyHtml += `<blockquote>${bqLines.join('<br>')}</blockquote>`;

  return html + bodyHtml;
}

function updateRenderedArtifact(text, file, runId = state.currentRun?.id || '') {
  if (!els.artifactRendered) return;
  const activeFile = file || state.selectedFile || '';
  if (activeFile.endsWith('.svg')) {
    const url = `/api/runs/${encodeURIComponent(runId)}/artifact?file=${encodeURIComponent(activeFile)}`;
    els.artifactRendered.innerHTML = `<img class="artifact-image" src="${escapeHtml(url)}" alt="${escapeHtml(activeFile)}">`;
    return;
  }
  if (activeFile.endsWith('.zip')) {
    els.artifactRendered.innerHTML = `<div class="paper-abstract"><p class="paper-abstract-title">📦 二进制归档包</p><p>产物文件：<code>${escapeHtml(activeFile)}</code></p><p>请使用右上角【下载文件】获取完整包。</p></div>`;
    return;
  }
  if (!text) {
    els.artifactRendered.innerHTML = '<p class="muted">尚未生成产物内容。</p>';
    return;
  }
  els.artifactRendered.innerHTML = formatAcademicMarkdown(text, activeFile);
}

async function loadArtifact(file) {
  const requestSequence = ++state.artifactLoadSequence;
  if (state.artifactLoadController) state.artifactLoadController.abort();
  const controller = new AbortController();
  state.artifactLoadController = controller;
  state.selectedFile = file;
  updateTabs();
  clearGoldLaunchCommands();
  els.artifactTitle.textContent = file;
  if (!state.currentRun) {
    els.artifactContent.textContent = '提交一个课题后，这里会显示论文、分析和实验结果。';
    els.downloadLink.href = '#';
    updateRenderedArtifact('', file, '');
    if (requestSequence === state.artifactLoadSequence) state.artifactLoadController = null;
    return;
  }
  const runId = state.currentRun.id;
  const url = `/api/runs/${encodeURIComponent(runId)}/artifact?file=${encodeURIComponent(file)}`;
  els.downloadLink.href = url;
  els.downloadLink.download = file;
  if (!(state.currentRun.artifacts || []).includes(file)) {
    els.artifactContent.textContent = missingArtifactMessage(state.currentRun);
    if (requestSequence === state.artifactLoadSequence) state.artifactLoadController = null;
    return;
  }
  if (file.endsWith('.svg')) {
    els.artifactContent.innerHTML = `<img class="artifact-image" src="${escapeHtml(url)}" alt="${escapeHtml(file)}">`;
    updateRenderedArtifact('', file, runId);
    if (requestSequence === state.artifactLoadSequence) state.artifactLoadController = null;
    return;
  }
  if (file.endsWith('.zip')) {
    els.artifactContent.textContent = `这是二进制 ZIP 产物：${file}\n\n请使用右上角下载按钮获取。`;
    updateRenderedArtifact('', file, runId);
    if (requestSequence === state.artifactLoadSequence) state.artifactLoadController = null;
    return;
  }
  try {
    const response = await fetch(url, {signal: controller.signal});
    const text = await response.text();
    if (!response.ok) throw new Error(errorMessageFromResponse(text, response.status));
    if (
      requestSequence !== state.artifactLoadSequence
      || controller.signal.aborted
      || state.currentRun?.id !== runId
      || state.selectedFile !== file
    ) return;
    els.artifactContent.textContent = text;
    updateRenderedArtifact(text, file, runId);
  } catch (error) {
    if (error.name !== 'AbortError' && requestSequence === state.artifactLoadSequence) {
      const message = `加载产物失败：${error.message}`;
      els.artifactContent.textContent = message;
      updateRenderedArtifact(message, file, runId);
    }
  } finally {
    if (requestSequence === state.artifactLoadSequence) state.artifactLoadController = null;
  }
}

function missingArtifactMessage(run) {
  if (run.status === 'cancelled') {
    return '该 run 已取消。已生成的产物仍可查看，取消记录保存在 cancel.json。';
  }
  if (run.status === 'cancelling') {
    return '已发送停止请求。当前步骤结束或审批等待轮询命中后会停止。';
  }
  if (run.status === 'failed') {
    return diagnosticMessage(run);
  }
  if (run.status === 'revision_requested' || run.stage === 'review_revision_requested') {
    const notes = run.approval?.notes ? `\n\n审核意见：${run.approval.notes}` : '';
    return `该 run 已被退回修改，未进入 Ideas 和实验。调整文献、人工种子文献或审核意见后，可点击“批准并恢复”；系统会先重新生成文献门禁，再决定是否进入后续阶段。${notes}`;
  }
  if (run.status === 'unknown') {
    return '该 run 没有活动后台线程。若产物已到达某个检查点，可以点击“恢复”从已有 JSON 产物继续。';
  }
  if (run.stage === 'awaiting_review_approval' && !run.approval?.approved) {
    const retrievalDetails = literatureRetrievalGateDetails(run);
    const evidenceDetails = literatureEvidenceContractDetails(run);
    const gateDetails = literatureQualityGateDetails(run);
    return ['已生成审核材料，等待人工批准后才会进入 Ideas 和实验。请查看“审核”或“批准记录”。', retrievalDetails, evidenceDetails, gateDetails].filter(Boolean).join('\n\n');
  }
  if (run.stage === 'awaiting_execution_approval' && !run.execution_approval?.approved) {
    const ideaGateDetails = ideaExperimentGateDetails(run);
    return ['已生成实验计划和执行安全审计。local/benchmark 模式需要人工查看“执行确认”和“执行安全”后批准，系统才会运行本地命令。', ideaGateDetails].filter(Boolean).join('\n\n');
  }
  if (run.stage === 'review_approved' || run.status === 'running') {
    return '已批准继续，后续产物正在生成。';
  }
  if (run.status === 'unknown' && run.stage === 'awaiting_review_approval') {
    return '该 run 停在审核门槛，但当前后台工作线程不存在。点击“批准并恢复”后会从审核门继续执行。';
  }
  return '该产物不可用。';
}

function diagnosticMessage(run) {
  const diagnostic = run.diagnostic;
  if (!diagnostic) {
    return run.error ? `运行失败：${run.error}` : '运行失败，请查看后台日志。';
  }
  const actionCount = Number(diagnostic.recommended_actions || 0);
  return [
    `运行失败：${diagnostic.summary || run.error || '未知错误'}`,
    '',
    `类型：${diagnostic.category || 'unknown'}`,
    `阶段：${diagnostic.stage || run.stage || 'unknown'}`,
    '',
    '可能原因：',
    diagnostic.likely_cause || '暂无',
    '',
    `建议动作数：${actionCount}`,
    '',
    run.artifacts?.includes('run-diagnostics.md') ? '可打开“诊断”查看公开摘要；完整 traceback 保留在本地 run 目录。' : '',
  ].filter((line) => line !== '').join('\n');
}

function payloadFromForm() {
  const form = new FormData(els.form);
  return {
    topic: String(form.get('topic') || '').trim(),
    paper_grade_enabled: form.get('paper_grade_enabled') === 'on',
    execution_mode: form.get('execution_mode'),
    llm_provider: form.get('llm_provider'),
    llm_base_url: String(form.get('llm_base_url') || '').trim(),
    llm_model: String(form.get('llm_model') || '').trim(),
    llm_api_key: String(form.get('llm_api_key') || '').trim(),
    llm_max_calls: Number(form.get('llm_max_calls') || 0),
    llm_max_prompt_chars: Number(form.get('llm_max_prompt_chars') || 0),
    llm_input_cost_per_million_tokens: Number(form.get('llm_input_cost_per_million_tokens') || 0),
    llm_output_cost_per_million_tokens: Number(form.get('llm_output_cost_per_million_tokens') || 0),
    human_notes: String(form.get('human_notes') || '').trim(),
    human_constraints: String(form.get('human_constraints') || '').trim(),
    human_success_criteria: String(form.get('human_success_criteria') || '').trim(),
    human_resource_limits: String(form.get('human_resource_limits') || '').trim(),
    human_risks: String(form.get('human_risks') || '').trim(),
    literature_provider: form.get('literature_provider'),
    literature_sources: String(form.get('literature_sources') || 'semantic_scholar, openalex, arxiv, crossref'),
    semantic_scholar_api_key: String(form.get('semantic_scholar_api_key') || '').trim(),
    openalex_api_key: String(form.get('openalex_api_key') || '').trim(),
    literature_contact_email: String(form.get('literature_contact_email') || '').trim(),
    extra_search_queries: String(form.get('extra_search_queries') || '').trim(),
    seed_papers: String(form.get('seed_papers') || '').trim(),
    fulltext_paths: String(form.get('fulltext_paths') || '').trim(),
    review_notes: String(form.get('review_notes') || '').trim(),
    benchmark_pack_run_dir: String(form.get('benchmark_pack_run_dir') || '').trim(),
    fulltext_grounding_run_dir: String(form.get('fulltext_grounding_run_dir') || '').trim(),
    max_papers: Number(form.get('max_papers') || 8),
    max_search_queries: Number(form.get('max_search_queries') || 4),
    max_ideas: Number(form.get('max_ideas') || 5),
    execution_repeats: Number(form.get('execution_repeats') || 5),
    timeout_seconds: Number(form.get('timeout_seconds') || 300),
    allowed_commands: String(form.get('allowed_commands') || 'python3, pytest'),
    benchmark_manifests: String(form.get('benchmark_manifests') || '').trim(),
    release_code_repository_url: String(form.get('release_code_repository_url') || '').trim(),
    release_code_archive_doi: String(form.get('release_code_archive_doi') || '').trim(),
    release_code_license: String(form.get('release_code_license') || '').trim(),
    release_code_version: String(form.get('release_code_version') || '').trim(),
    release_data_repository_url: String(form.get('release_data_repository_url') || '').trim(),
    release_data_archive_doi: String(form.get('release_data_archive_doi') || '').trim(),
    release_data_access_statement: String(form.get('release_data_access_statement') || '').trim(),
    release_environment_url: String(form.get('release_environment_url') || '').trim(),
    release_notes: String(form.get('release_notes') || '').trim(),
    target_venue: form.get('target_venue'),
    paper_style: form.get('paper_style'),
  };
}

function setFieldValue(name, value) {
  const field = els.form.elements.namedItem(name);
  if (field) field.value = String(value);
}

function setNumberMinimum(name, value) {
  const field = els.form.elements.namedItem(name);
  if (!field) return;
  const current = Number(field.value || 0);
  field.value = String(Math.max(current, value));
}

function appendTextareaLines(name, lines) {
  const field = els.form.elements.namedItem(name);
  if (!field) return [];
  const existing = textareaLines(name);
  const seen = new Set(existing.map((item) => item.toLowerCase()));
  const added = [];
  for (const line of lines) {
    const value = String(line || '').trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) continue;
    existing.push(value);
    seen.add(key);
    added.push(value);
  }
  field.value = existing.join('\n');
  return added;
}

function textareaLines(name) {
  const field = els.form.elements.namedItem(name);
  if (!field) return [];
  return String(field.value || '').split('\n').map((item) => item.trim()).filter(Boolean);
}

function ensureCommaListValue(name, value) {
  const field = els.form.elements.namedItem(name);
  if (!field) return;
  const items = String(field.value || '').split(',').map((item) => item.trim()).filter(Boolean);
  if (!items.some((item) => item.toLowerCase() === String(value).toLowerCase())) {
    items.push(String(value));
  }
  field.value = items.join(', ');
}

function missingReleaseFormFields(fieldNames) {
  if (!Array.isArray(fieldNames)) return [];
  const knownFields = new Set(Object.values(releaseFormFieldByConfigKey));
  const seen = new Set();
  const missing = [];
  for (const fieldName of fieldNames) {
    const name = String(fieldName || '').trim();
    if (!knownFields.has(name) || seen.has(name)) continue;
    seen.add(name);
    const field = els.form.elements.namedItem(name);
    if (field && !String(field.value || '').trim()) missing.push(name);
  }
  return missing;
}

function releaseFieldLabel(fieldName) {
  return releaseFormFieldLabels[fieldName] || fieldName;
}

function hasActiveRunWork() {
  return state.runs.some((run) => run.worker_active === true || run.status === 'cancelling');
}

function stopPolling() {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

async function pollRunsOnce() {
  state.pollTimer = null;
  if (state.pollInFlight || document.hidden || !hasActiveRunWork()) return;
  state.pollInFlight = true;
  try {
    await refreshRuns(true, false);
  } catch (error) {
    if (error.name !== 'AbortError') console.error(error);
  } finally {
    state.pollInFlight = false;
    if (!document.hidden && hasActiveRunWork()) startPolling();
  }
}

function startPolling() {
  stopPolling();
  if (state.pollInFlight || document.hidden || !hasActiveRunWork()) return;
  state.pollTimer = window.setTimeout(pollRunsOnce, 4000);
}

els.form.addEventListener('submit', async (event) => {
  event.preventDefault();
  switchView('view-workbench');
  els.submit.disabled = true;
  try {
    const run = await api('/api/runs', {
      method: 'POST',
      body: JSON.stringify(payloadForRunAction()),
    });
    setCurrentRun(run);
    await refreshRuns(true);
    await loadArtifact(state.selectedFile);
    startPolling();
  } catch (error) {
    els.artifactContent.textContent = `启动失败：${error.message}`;
  } finally {
    els.submit.disabled = false;
  }
});

els.form.addEventListener('input', () => {
  updateActionButtons();
});

els.refresh.addEventListener('click', () => refreshRuns(true));
els.summary.addEventListener('click', loadRunSummary);
els.platformAudit.addEventListener('click', loadPlatformAudit);
els.perfectReadiness.addEventListener('click', loadPerfectReadiness);
els.openSourceBackfillPreview.addEventListener('click', previewOpenSourceBackfill);
els.openSourceBackfillRun.addEventListener('click', runOpenSourceBackfill);
els.llmBackfillPreview.addEventListener('click', previewLlmObservabilityBackfill);
els.llmBackfillRun.addEventListener('click', runLlmObservabilityBackfill);
els.repairBacklog.addEventListener('click', loadRepairResumeBacklog);
els.repairBackfillPreview.addEventListener('click', previewRepairResumeBackfill);
els.repairBackfillRun.addEventListener('click', runRepairResumeBackfill);
els.applyMemoryDefaults.addEventListener('click', applyMemoryDefaultsToForm);
els.applyGoldDefaults.addEventListener('click', applyGoldDefaultsToForm);
els.goldDefaultsSmoke.addEventListener('click', runGoldDefaultsSmoke);
els.librarySearch.addEventListener('click', loadRunLibrary);
els.libraryQuery.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    loadRunLibrary();
  }
});
els.preflight.addEventListener('click', runPreflight);
els.envLlmPreflight.addEventListener('click', runEnvLlmPreflight);
els.goldEnvLint.addEventListener('click', lintGoldEnv);
els.goldEnvLaunchKit.addEventListener('click', showGoldEnvLaunchKit);
els.goldLaunchBundle.addEventListener('click', runGoldLaunchBundle);
els.goldRunLaunch.addEventListener('click', runGoldLaunch);
els.paperGradeProbe.addEventListener('click', runPaperGradeProbe);
els.goldRunDoctor.addEventListener('click', runGoldDoctor);
els.goldRunVerify.addEventListener('click', runGoldVerify);
els.copyGoldLaunchCommands.addEventListener('click', copyGoldLaunchCommands);
els.literaturePreview.addEventListener('click', previewLiterature);
els.applyLiteraturePreviewSeeds.addEventListener('click', applyLiteraturePreviewSeedsToForm);
els.benchmarkPreview.addEventListener('click', previewBenchmark);
els.benchmarkTemplate.addEventListener('click', showBenchmarkTemplate);
els.benchmarkManifestLint.addEventListener('click', lintBenchmarkManifestDraft);
els.benchmarkManifestSave.addEventListener('click', saveBenchmarkManifestDraft);
els.benchmarkExample.addEventListener('click', applyBenchmarkExampleToForm);
els.releaseMetadataLint.addEventListener('click', lintReleaseMetadata);
els.approve.addEventListener('click', approveCurrentRun);
els.revision.addEventListener('click', requestRevisionCurrentRun);
els.repairResumePreview.addEventListener('click', previewRepairResumeCurrentRun);
els.applyRepairResume.addEventListener('click', applyRepairResumePreviewToForm);
els.resume.addEventListener('click', resumeCurrentRun);
els.applyLiteratureFeedback.addEventListener('click', applyLiteratureFeedbackToForm);
els.cancel.addEventListener('click', cancelCurrentRun);

if (window.MutationObserver && els.artifactTitle) {
  new MutationObserver(clearGoldLaunchCommandsWhenArtifactChanges)
    .observe(els.artifactTitle, {childList: true, characterData: true, subtree: true});
}

els.runList.addEventListener('click', (event) => {
  const button = event.target.closest('[data-id]');
  if (button) loadRun(button.dataset.id);
});

els.tabs.forEach((tab) => {
  tab.addEventListener('click', () => loadArtifact(tab.dataset.file));
});

renderStages('started');
refreshRuns(false).then(startPolling).catch((error) => {
  els.artifactContent.textContent = `加载失败：${error.message}`;
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopPolling();
    return;
  }
  refreshRuns(true, true).then(startPolling).catch((error) => {
    if (error.name !== 'AbortError') console.error(error);
  });
});


if (els.btnViewAcademic && els.btnViewRaw) {
  els.btnViewAcademic.addEventListener('click', () => {
    els.btnViewAcademic.classList.add('active');
    els.btnViewRaw.classList.remove('active');
    els.btnViewAcademic.setAttribute('aria-pressed', 'true');
    els.btnViewRaw.setAttribute('aria-pressed', 'false');
    if (els.artifactRendered) els.artifactRendered.hidden = false;
    if (els.artifactContent) els.artifactContent.hidden = true;
  });
  els.btnViewRaw.addEventListener('click', () => {
    els.btnViewRaw.classList.add('active');
    els.btnViewAcademic.classList.remove('active');
    els.btnViewRaw.setAttribute('aria-pressed', 'true');
    els.btnViewAcademic.setAttribute('aria-pressed', 'false');
    if (els.artifactRendered) els.artifactRendered.hidden = true;
    if (els.artifactContent) els.artifactContent.hidden = false;
  });
}

if (els.catFilterBtns && els.catFilterBtns.length) {
  els.catFilterBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      els.catFilterBtns.forEach((b) => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      const cat = btn.dataset.cat || 'all';
      els.tabs.forEach((tab) => {
        if (cat === 'all' || tab.dataset.cat === cat) {
          tab.style.display = '';
        } else {
          tab.style.display = 'none';
        }
      });
    });
  });
}

if (window.MutationObserver && els.artifactContent) {
  new MutationObserver(() => {
    updateRenderedArtifact(els.artifactContent.textContent, state.selectedFile);
  }).observe(els.artifactContent, {childList: true, characterData: true, subtree: true});
}


document.querySelectorAll('.nav-tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.dataset.view) switchView(btn.dataset.view);
  });
});

const pagePrevBtn = document.querySelector('#page-prev');
if (pagePrevBtn) {
  pagePrevBtn.addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      renderRunList();
    }
  });
}

const pageNextBtn = document.querySelector('#page-next');
if (pageNextBtn) {
  pageNextBtn.addEventListener('click', () => {
    state.currentPage++;
    renderRunList();
  });
}

const pageNumbersContainer = document.querySelector('#page-numbers');
if (pageNumbersContainer) {
  pageNumbersContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-page]');
    if (btn) {
      state.currentPage = Number(btn.dataset.page);
      renderRunList();
    }
  });
}


const testLlmBtn = document.querySelector('#test-llm-connection');
const testLlmStatus = document.querySelector('#llm-connection-status');

function envLlmConnectionResult(response) {
  const env = response?.env_llm || {};
  const failed = Array.isArray(env.failed_llm_checks) ? env.failed_llm_checks : [];
  const configured = env.server_env_configured || {};
  const configuredCount = ['base_url', 'model', 'api_key'].filter((key) => configured[key] === true).length;
  if (env.status === 'pass') {
    return {
      status: 'pass',
      summary: '服务端 LLM 环境与 Ping 均正常',
      detail: `环境变量 3/3，ping=${env.ping_status || 'pass'}`,
    };
  }
  if (env.status === 'warn') {
    return {
      status: 'warn',
      summary: '服务端 LLM 环境需要复核',
      detail: `环境变量 ${configuredCount}/3，ping=${env.ping_status || 'unknown'}`,
      action: '检查 Web 服务启动终端中的 OPENAI_BASE_URL、OPENAI_MODEL 和 OPENAI_API_KEY。',
    };
  }
  return {
    status: 'fail',
    summary: '服务端 LLM 环境未就绪',
    detail: failed.length ? `失败项：${failed.join(', ')}` : `环境变量 ${configuredCount}/3，ping=${env.ping_status || 'unknown'}`,
    action: '在启动 Web 服务前设置 OPENAI_BASE_URL、OPENAI_MODEL 和 OPENAI_API_KEY，然后重启服务。',
  };
}

if (testLlmBtn) {
  testLlmBtn.addEventListener('click', async () => {
    const requestSequence = ++state.llmPingSequence;
    if (state.llmPingController) state.llmPingController.abort();
    const controller = new AbortController();
    state.llmPingController = controller;
    const configVersion = state.llmConfigVersion;
    let browserTimeout = null;
    testLlmBtn.disabled = true;
    testLlmBtn.innerHTML = '<span>🔌 正在测试连通性...</span>';
    if (testLlmStatus) {
      testLlmStatus.style.display = 'inline-flex';
      testLlmStatus.innerHTML = '<span style="color:var(--muted);">正在向模型接口发送 Ping 探测请求...</span>';
    }
    try {
      const payload = payloadForRunAction();
      const useServerEnvironment = payload.paper_grade_enabled === true;
      if (!useServerEnvironment) validateLlmEndpointConfig({requireModel: true});
      payload.timeout_seconds = 8;
      payload.llm_timeout_seconds = 8;
      browserTimeout = window.setTimeout(() => controller.abort(), 10000);
      const response = await api(useServerEnvironment ? '/api/env-llm-preflight' : '/api/test-llm', {
        method: 'POST',
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (requestSequence !== state.llmPingSequence || configVersion !== state.llmConfigVersion) return;
      const res = useServerEnvironment ? envLlmConnectionResult(response) : response;
      if (res.status === 'pass') {
        const latency = Number.isFinite(Number(res.latency_ms)) ? ` (${Number(res.latency_ms)}ms)` : '';
        testLlmStatus.innerHTML = `<span style="color:var(--emerald-700); font-weight:700; background:var(--emerald-100); padding:4px 10px; border-radius:6px; border:1px solid #a7f3d0;">连通正常${latency} · ${escapeHtml(res.detail || res.summary)}</span>`;
      } else if (res.status === 'warn') {
        testLlmStatus.innerHTML = `<span style="color:var(--gold-700); font-weight:700; background:var(--gold-100); padding:4px 10px; border-radius:6px; border:1px solid #fde68a;">${escapeHtml(res.summary)} · ${escapeHtml(res.detail || res.action)}</span>`;
      } else if (res.status === 'skipped') {
        testLlmStatus.innerHTML = `<span style="color:var(--muted); background:#f1f5f9; padding:4px 10px; border-radius:6px; border:1px solid var(--line);">${escapeHtml(res.summary)}: ${escapeHtml(res.action || res.detail)}</span>`;
      } else {
        testLlmStatus.innerHTML = `<span style="color:var(--crimson-700); font-weight:700; background:var(--crimson-100); padding:4px 10px; border-radius:6px; border:1px solid #fca5a5;">连接失败 · ${escapeHtml(res.detail || res.summary)} ${res.action ? '(' + escapeHtml(res.action) + ')' : ''}</span>`;
      }
    } catch (err) {
      if (requestSequence === state.llmPingSequence && configVersion === state.llmConfigVersion) {
        testLlmStatus.innerHTML = `<span style="color:var(--crimson-700); font-weight:700; background:var(--crimson-100); padding:4px 10px; border-radius:6px; border:1px solid #fca5a5;">连接失败 · ${escapeHtml(llmConnectionErrorMessage(err))}</span>`;
      }
    } finally {
      if (browserTimeout) window.clearTimeout(browserTimeout);
      if (requestSequence === state.llmPingSequence) {
        state.llmPingController = null;
        testLlmBtn.disabled = false;
        syncPaperGradeSecretPolicy();
      }
    }
  });
}


// Provider Base URL presets & auto-fill
const PROVIDER_DEFAULTS = {
  'openai-compatible': { url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  'deepseek': { url: 'https://api.deepseek.com', model: 'deepseek-chat' },
  'dashscope': { url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  'zhipu': { url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus' },
  'moonshot': { url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  'siliconflow': { url: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
  'openrouter': { url: 'https://openrouter.ai/api/v1', model: 'anthropic/claude-3.5-sonnet' },
  'google-gemini': { url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.0-flash' },
  'anthropic-compatible': { url: '', model: 'claude-3-5-sonnet-20241022' },
  'ollama': { url: 'http://localhost:11434/v1', model: 'llama3.2' },
  'vllm': { url: 'http://localhost:8000/v1', model: 'default-model' },
  'azure-openai': { url: '', model: '' },
  'custom-http': { url: '', model: '' }
};

const providerSelect = document.querySelector('#llm-provider');
const baseUrlInput = document.querySelector('#llm-base-url');
const modelInput = document.querySelector('#llm-model');
const modelDatalist = document.querySelector('#llm-model-datalist');
const modelChipsBox = document.querySelector('#llm-model-chips');
const btnFetchModels = document.querySelector('#btn-fetch-models');
const apiKeyInput = document.querySelector('#llm-api-key');
const paperGradeInput = document.querySelector('#paper-grade-enabled');
const llmApiKeyPolicy = document.querySelector('#llm-api-key-policy');
const paperGradeSecretInputs = [...document.querySelectorAll('[data-paper-grade-secret]')];

function clearModelOptions() {
  if (modelDatalist) modelDatalist.innerHTML = '';
  if (modelChipsBox) {
    modelChipsBox.innerHTML = '';
    modelChipsBox.hidden = true;
  }
}

function invalidateLlmConnectionStatus({clearModels = false} = {}) {
  state.llmConfigVersion += 1;
  if (state.llmPingController) state.llmPingController.abort();
  if (state.modelFetchController) state.modelFetchController.abort();
  if (testLlmStatus) {
    testLlmStatus.textContent = '';
    testLlmStatus.style.display = 'none';
  }
  if (clearModels) clearModelOptions();
}

function validateLlmEndpointConfig({requireModel = false} = {}) {
  const provider = String(providerSelect?.value || 'openai-compatible').trim();
  const baseUrl = String(baseUrlInput?.value || '').trim();
  const model = String(modelInput?.value || '').trim();
  if (provider === 'azure-openai' || provider === 'anthropic-compatible') {
    throw new Error('当前版本未实现该 Provider 的原生协议，请改用 OpenAI-Compatible 网关并选择对应兼容 Provider。');
  }
  if (!baseUrl) throw new Error('请填写明确的 OpenAI-Compatible Base URL，前端不会自动回退到 OpenAI 官方地址。');
  if (baseUrl) {
    let parsed;
    try {
      parsed = new URL(baseUrl);
    } catch (error) {
      throw new Error('Base URL 格式无效，必须是完整的 http:// 或 https:// 地址。');
    }
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      throw new Error('Base URL 仅支持 http:// 或 https:// 地址。');
    }
  }
  if (requireModel && !model) throw new Error('请先填写模型名称。');
}

function llmConnectionErrorMessage(error) {
  const message = String(error?.message || error || '未知错误');
  if (/429|concurrency limit exceeded|rate_limit_error/i.test(message)) {
    return '网关并发额度已满（HTTP 429）。等待当前请求结束后再重试；这通常不是 Base URL、模型名或 API Key 错误。';
  }
  if (error?.name === 'AbortError') return 'Ping 在 10 秒内未完成，已停止等待。请检查网关负载和服务状态。';
  return message;
}

function syncPaperGradeSecretPolicy() {
  const envOnly = Boolean(paperGradeInput?.checked);
  paperGradeSecretInputs.forEach((input) => {
    input.disabled = envOnly;
    input.setAttribute('aria-disabled', envOnly ? 'true' : 'false');
  });
  if (llmApiKeyPolicy) {
    llmApiKeyPolicy.classList.toggle('is-env-only', envOnly);
    llmApiKeyPolicy.textContent = envOnly
      ? 'Paper-Grade 使用 Web 服务进程中的 OPENAI_API_KEY；表单密钥不会发送。'
      : '普通模式可为本次请求临时提供 Key；配置快照不会保存密钥。';
  }
  if (btnFetchModels) {
    btnFetchModels.disabled = envOnly;
    btnFetchModels.textContent = envOnly ? '使用服务端环境 Ping' : '查询接口模型';
    btnFetchModels.title = envOnly ? 'Paper-Grade 不通过 Web 表单发送密钥' : '查询接口实时返回的模型列表';
  }
  if (testLlmBtn && !testLlmBtn.disabled) {
    testLlmBtn.innerHTML = `<span>${envOnly ? '测试服务端 LLM 环境' : '测试模型与 Key 连通性 (Ping)'}</span>`;
  }
}

if (paperGradeInput) {
  paperGradeInput.addEventListener('change', () => {
    invalidateLlmConnectionStatus({clearModels: true});
    syncPaperGradeSecretPolicy();
  });
}

if (providerSelect && baseUrlInput) {
  providerSelect.addEventListener('change', () => {
    const selected = providerSelect.value;
    const preset = PROVIDER_DEFAULTS[selected];
    const presetUrls = new Set(Object.values(PROVIDER_DEFAULTS).map((item) => item.url).filter(Boolean));
    const presetModels = new Set(Object.values(PROVIDER_DEFAULTS).map((item) => item.model).filter(Boolean));
    if (preset) {
      if (!baseUrlInput.value || presetUrls.has(baseUrlInput.value)) {
        baseUrlInput.value = preset.url;
      }
      if (!modelInput.value || presetModels.has(modelInput.value)) {
        modelInput.value = preset.model;
      }
    }
    invalidateLlmConnectionStatus({clearModels: true});
  });
}

if (baseUrlInput) baseUrlInput.addEventListener('input', () => invalidateLlmConnectionStatus({clearModels: true}));
if (apiKeyInput) apiKeyInput.addEventListener('input', () => invalidateLlmConnectionStatus({clearModels: true}));
if (modelInput) modelInput.addEventListener('input', () => invalidateLlmConnectionStatus());

function renderModelOptions(models, source) {
  if (!models || !models.length) return;
  if (modelDatalist) {
    modelDatalist.innerHTML = models.map(m => `<option value="${escapeHtml(m)}"></option>`).join('');
  }
  if (modelChipsBox) {
    modelChipsBox.hidden = false;
    modelChipsBox.innerHTML = `
      <div style="width:100%; font-size:11px; color:var(--muted); margin-bottom:2px;">
        ${source === 'live_api' ? '⚡ 接口实时获取到的可用模型 (点击直接使用)：' : '💡 推荐模型列表 (点击直接使用)：'}
      </div>
      ` + models.map(m => `
        <button type="button" class="mini-button model-chip-btn" data-model="${escapeHtml(m)}" style="height:24px; padding:0 8px; font-size:11px; background:${modelInput.value === m ? 'var(--navy-900)' : '#f1f5f9'}; color:${modelInput.value === m ? '#fff' : 'var(--navy-900)'};">
          ${escapeHtml(m)}
        </button>
      `).join('');
  }
}

if (modelChipsBox) {
  modelChipsBox.addEventListener('click', (e) => {
    const btn = e.target.closest('.model-chip-btn');
    if (btn && btn.dataset.model) {
      modelInput.value = btn.dataset.model;
      invalidateLlmConnectionStatus();
      document.querySelectorAll('.model-chip-btn').forEach(b => {
        const isCur = b.dataset.model === btn.dataset.model;
        b.style.background = isCur ? 'var(--navy-900)' : '#f1f5f9';
        b.style.color = isCur ? '#fff' : 'var(--navy-900)';
      });
    }
  });
}

if (btnFetchModels) {
  btnFetchModels.addEventListener('click', async () => {
    const requestSequence = ++state.modelFetchSequence;
    if (state.modelFetchController) state.modelFetchController.abort();
    const controller = new AbortController();
    state.modelFetchController = controller;
    const configVersion = state.llmConfigVersion;
    let browserTimeout = null;
    btnFetchModels.disabled = true;
    btnFetchModels.innerHTML = '🔄 查询中...';
    try {
      validateLlmEndpointConfig();
      const payload = {
        llm_provider: providerSelect ? providerSelect.value : 'openai-compatible',
        llm_base_url: baseUrlInput ? baseUrlInput.value.trim() : '',
        llm_api_key: paperGradeInput?.checked ? '' : (apiKeyInput ? apiKeyInput.value : ''),
        timeout_seconds: 8,
      };
      browserTimeout = window.setTimeout(() => controller.abort(), 10000);
      const res = await api('/api/fetch-models', {
        method: 'POST',
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (requestSequence !== state.modelFetchSequence || configVersion !== state.llmConfigVersion) return;
      if (res.models && res.models.length) {
        renderModelOptions(res.models, res.source);
        const liveSuccess = res.success === true && res.source === 'live_api';
        if (liveSuccess && !modelInput.value) {
          modelInput.value = res.models[0];
        }
        if (testLlmStatus) {
          testLlmStatus.style.display = 'inline-flex';
          testLlmStatus.innerHTML = liveSuccess
            ? `<span style="color:var(--emerald-700); font-weight:700; background:var(--emerald-100); padding:3px 8px; border-radius:4px; border:1px solid #a7f3d0;">接口已验证 ${res.models.length} 个可用模型</span>`
            : `<span style="color:var(--gold-700); font-weight:700; background:var(--gold-100); padding:3px 8px; border-radius:4px; border:1px solid #fde68a;">实时查询失败：${escapeHtml(res.error || '接口未返回模型')}。下方仅为推荐预设，使用前必须通过 Ping。</span>`;
        }
      }
    } catch (err) {
      if (testLlmStatus && requestSequence === state.modelFetchSequence && configVersion === state.llmConfigVersion) {
        testLlmStatus.style.display = 'inline-flex';
        testLlmStatus.innerHTML = `<span style="color:var(--crimson-700); font-weight:700; background:var(--crimson-100); padding:3px 8px; border-radius:4px; border:1px solid #fca5a5;">获取模型失败：${escapeHtml(llmConnectionErrorMessage(err))}</span>`;
      }
    } finally {
      if (browserTimeout) window.clearTimeout(browserTimeout);
      if (requestSequence === state.modelFetchSequence) {
        state.modelFetchController = null;
        syncPaperGradeSecretPolicy();
      }
    }
  });
}

syncPaperGradeSecretPolicy();
