from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import tomllib


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai-compatible"
    base_url_env: str = "OPENAI_BASE_URL"
    api_key_env: str = "OPENAI_API_KEY"
    model_env: str = "OPENAI_MODEL"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_calls: int = 0
    max_prompt_chars: int = 0
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0
    temperature: float | None = None
    max_tokens: int | None = None
    # COST-01: per-model price overrides, keyed by model name with
    # input/output_cost_per_million_tokens entries; the global prices apply
    # to models not listed here.
    model_costs: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class LiteratureConfig:
    provider: str = "offline"
    max_papers: int = 8
    sources: list[str] = field(default_factory=lambda: ["semantic_scholar", "openalex", "arxiv", "crossref"])
    extra_search_queries: list[str] = field(default_factory=list)
    seed_papers: list[str] = field(default_factory=list)
    fulltext_paths: list[str] = field(default_factory=list)
    timeout_seconds: int = 12
    max_search_queries: int = 4
    min_relevance: float = 0.24
    cache_enabled: bool = True
    cache_dir: str = ".cache/research-agent/literature"
    cache_ttl_seconds: int = 604800
    semantic_scholar_api_key_env: str = "SEMANTIC_SCHOLAR_API_KEY"
    openalex_api_key_env: str = "OPENALEX_API_KEY"
    contact_email_env: str = "RESEARCH_AGENT_CONTACT_EMAIL"
    semantic_scholar_api_key: str = ""
    openalex_api_key: str = ""
    contact_email: str = ""


@dataclass(frozen=True)
class IdeationConfig:
    max_ideas: int = 5


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "simulated"
    timeout_seconds: int = 300
    allowed_commands: list[str] = field(default_factory=lambda: ["python3", "pytest"])
    repeats: int = 5
    benchmark_manifest_paths: list[str] = field(default_factory=list)
    max_output_bytes: int = 1_048_576
    external_runner_controlled: bool = False
    # Simulated-mode per-command-mode "advantage" offsets; empty by default so
    # the deterministic jitter alone decides which command wins.
    simulated_offsets: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperConfig:
    target_venue: str = "workshop"
    style: str = "concise"


@dataclass(frozen=True)
class ReleaseConfig:
    code_repository_url: str = ""
    code_archive_doi: str = ""
    code_license: str = ""
    code_version: str = ""
    data_repository_url: str = ""
    data_archive_doi: str = ""
    data_access_statement: str = ""
    environment_url: str = ""
    release_notes: str = ""


@dataclass(frozen=True)
class PaperGradeConfig:
    enabled: bool = False
    min_literature_sources: int = 3
    min_successful_literature_sources: int = 2
    min_seed_papers: int = 3
    min_doi_url_seed_papers: int = 3
    min_curated_seed_roles: int = 3
    min_benchmark_roles: int = 3
    min_execution_repeats: int = 3


@dataclass(frozen=True)
class HumanConfig:
    notes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    resource_limits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRoleConfig:
    """Per-role runtime overrides; credentials always come from ``LLMConfig``.

    ``base_url``/``base_url_env``/``api_key_env`` let a role target a different
    OpenAI-compatible endpoint. Literal API keys stay global: a role may only
    point at an env variable, and ``resolve_llm_api_key`` still refuses to send
    an env credential to a URL that does not match its declared origin.
    """

    agent_id: str
    model: str = ""
    enabled: bool = True
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    base_url: str = ""
    base_url_env: str = ""
    api_key_env: str = ""


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    transport: str = "streamable-http"
    url: str = ""
    command: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    auth_env: str = ""
    enabled: bool = False
    read_only: bool = True
    allow_remote: bool = False


@dataclass(frozen=True)
class MultiAgentConfig:
    enabled: bool = False
    roles: list[AgentRoleConfig] = field(default_factory=list)
    task_models: dict[str, str] = field(default_factory=dict)
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    max_tool_rounds: int = 2
    tool_timeout_seconds: int = 15
    max_tool_output_chars: int = 16_000


@dataclass(frozen=True)
class AgentConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    literature: LiteratureConfig = field(default_factory=LiteratureConfig)
    ideation: IdeationConfig = field(default_factory=IdeationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    paper_grade: PaperGradeConfig = field(default_factory=PaperGradeConfig)
    human: HumanConfig = field(default_factory=HumanConfig)
    multi_agent: MultiAgentConfig = field(default_factory=MultiAgentConfig)


def load_config(path: Path | None) -> AgentConfig:
    if path is None:
        return AgentConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return AgentConfig(
        llm=LLMConfig(**data.get("llm", {})),
        literature=LiteratureConfig(**data.get("literature", {})),
        ideation=IdeationConfig(**data.get("ideation", {})),
        execution=ExecutionConfig(**data.get("execution", {})),
        paper=PaperConfig(**data.get("paper", {})),
        release=ReleaseConfig(**data.get("release", {})),
        paper_grade=PaperGradeConfig(**data.get("paper_grade", {})),
        human=HumanConfig(**data.get("human", {})),
        multi_agent=_multi_agent_config(data.get("multi_agent", {})),
    )


def load_config_snapshot(path: Path) -> AgentConfig:
    """Load the redacted JSON configuration persisted with an existing run."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid run config snapshot: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid run config snapshot: {path}")
    try:
        return config_from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid run config snapshot: {path}") from exc


def config_from_dict(data: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        llm=LLMConfig(**dict(data.get("llm") or {})),
        literature=LiteratureConfig(**dict(data.get("literature") or {})),
        ideation=IdeationConfig(**dict(data.get("ideation") or {})),
        execution=ExecutionConfig(**dict(data.get("execution") or {})),
        paper=PaperConfig(**dict(data.get("paper") or {})),
        release=ReleaseConfig(**dict(data.get("release") or {})),
        paper_grade=PaperGradeConfig(**dict(data.get("paper_grade") or {})),
        human=HumanConfig(**dict(data.get("human") or {})),
        multi_agent=_multi_agent_config(data.get("multi_agent", {})),
    )


def _multi_agent_config(value: Any) -> MultiAgentConfig:
    data = dict(value or {})
    roles_value = data.pop("roles", [])
    servers_value = data.pop("mcp_servers", [])
    task_models_value = data.get("task_models", {})
    if not isinstance(roles_value, list):
        raise TypeError("multi_agent.roles must be a list")
    if not isinstance(servers_value, list):
        raise TypeError("multi_agent.mcp_servers must be a list")
    if not isinstance(task_models_value, dict):
        raise TypeError("multi_agent.task_models must be an object")
    data["task_models"] = {
        str(stage).strip(): str(model).strip()
        for stage, model in task_models_value.items()
        if str(stage).strip() and str(model).strip()
    }
    return MultiAgentConfig(
        roles=[AgentRoleConfig(**dict(item)) for item in roles_value if isinstance(item, dict)],
        mcp_servers=[MCPServerConfig(**dict(item)) for item in servers_value if isinstance(item, dict)],
        **data,
    )
