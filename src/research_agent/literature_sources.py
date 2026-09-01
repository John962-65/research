from __future__ import annotations

from dataclasses import replace
from math import ceil
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from .config import LiteratureConfig
from .credential_validation import placeholder_secret, valid_contact_email
from .models import Paper


USER_AGENT = "research-agent/0.1 (+https://local.research-agent)"


class LiteratureSourceError(RuntimeError):
    pass


class OnlineLiteratureClient:
    def __init__(self, config: LiteratureConfig) -> None:
        self.config = config
        self.timeout = max(1, config.timeout_seconds)
        self.source_health: list[dict[str, Any]] = []
        self._cache_stats = {"hits": 0, "misses": 0, "writes": 0, "stale_uses": 0}

    def search(self, topic: str, queries: list[str] | None = None) -> tuple[list[Paper], list[str]]:
        papers: list[Paper] = []
        diagnostics: list[str] = []
        self.source_health = []
        source_map: dict[str, Callable[[str, int], list[Paper]]] = {
            "semantic_scholar": self.search_semantic_scholar,
            "openalex": self.search_openalex,
            "crossref": self.search_crossref,
            "arxiv": self.search_arxiv,
            "pubmed": self.search_pubmed,
        }
        search_queries = _normalize_queries(queries or [], topic, self.config.max_search_queries)
        diagnostics.append("检索式: " + " | ".join(search_queries))
        per_query_limit = max(4, ceil(max(self.config.max_papers * 3, 12) / max(len(search_queries), 1)))
        for source in self.config.sources:
            source = source.strip().lower()
            fetcher = source_map.get(source)
            if fetcher is None:
                diagnostics.append(f"跳过未知文献源：{source}")
                query_results = [
                    {
                        "source": source,
                        "query": query,
                        "status": "skipped",
                        "returned": 0,
                        "error": "unknown_source",
                        "rate_limited": False,
                        "elapsed_seconds": 0.0,
                        "cache_hits": 0,
                        "cache_misses": 0,
                        "cache_writes": 0,
                        "stale_cache_uses": 0,
                    }
                    for query in search_queries
                ]
                self.source_health.append(
                    {
                        "source": source,
                        "status": "skipped",
                        "queries": len(search_queries),
                        "returned": 0,
                        "errors": 0,
                        "rate_limited": False,
                        "elapsed_seconds": 0.0,
                        "cache_hits": 0,
                        "cache_misses": 0,
                        "cache_writes": 0,
                        "stale_cache_uses": 0,
                        "query_results": query_results,
                    }
                )
                continue
            start = time.monotonic()
            source_count = 0
            errors = 0
            rate_limited = False
            cache_before = dict(self._cache_stats)
            query_results: list[dict[str, Any]] = []
            for query in search_queries:
                query_start = time.monotonic()
                query_cache_before = dict(self._cache_stats)
                try:
                    result = fetcher(query, per_query_limit)
                except Exception as exc:
                    errors += 1
                    query_cache_delta = _cache_delta(query_cache_before, self._cache_stats)
                    safe_error = self._safe_error(exc)
                    diagnostics.append(f"{source}: query={query!r} 检索失败：{safe_error}")
                    if "HTTP 429" in str(exc) and source == "semantic_scholar":
                        rate_limited = True
                        query_results.append(
                            {
                                "source": source,
                                "query": query,
                                "status": "rate_limited",
                                "returned": 0,
                                "error": safe_error[:300],
                                "rate_limited": True,
                                "elapsed_seconds": round(time.monotonic() - query_start, 3),
                                "cache_hits": query_cache_delta["hits"],
                                "cache_misses": query_cache_delta["misses"],
                                "cache_writes": query_cache_delta["writes"],
                                "stale_cache_uses": query_cache_delta["stale_uses"],
                            }
                        )
                        diagnostics.append("semantic_scholar: 已限流，建议设置 SEMANTIC_SCHOLAR_API_KEY；本次继续使用其他来源。")
                        break
                    query_results.append(
                        {
                            "source": source,
                            "query": query,
                            "status": "failed",
                            "returned": 0,
                            "error": safe_error[:300],
                            "rate_limited": False,
                            "elapsed_seconds": round(time.monotonic() - query_start, 3),
                            "cache_hits": query_cache_delta["hits"],
                            "cache_misses": query_cache_delta["misses"],
                            "cache_writes": query_cache_delta["writes"],
                            "stale_cache_uses": query_cache_delta["stale_uses"],
                        }
                    )
                    continue
                source_count += len(result)
                papers.extend(result)
                query_cache_delta = _cache_delta(query_cache_before, self._cache_stats)
                query_results.append(
                    {
                        "source": source,
                        "query": query,
                        "status": "ok",
                        "returned": len(result),
                        "error": "",
                        "rate_limited": False,
                        "elapsed_seconds": round(time.monotonic() - query_start, 3),
                        "cache_hits": query_cache_delta["hits"],
                        "cache_misses": query_cache_delta["misses"],
                        "cache_writes": query_cache_delta["writes"],
                        "stale_cache_uses": query_cache_delta["stale_uses"],
                    }
                )
            elapsed = time.monotonic() - start
            cache_delta = _cache_delta(cache_before, self._cache_stats)
            status = "rate_limited" if rate_limited else "failed" if errors and source_count == 0 else "partial" if errors else "ok"
            self.source_health.append(
                {
                    "source": source,
                    "status": status,
                    "queries": len(search_queries),
                    "returned": source_count,
                    "errors": errors,
                    "rate_limited": rate_limited,
                    "elapsed_seconds": round(elapsed, 3),
                    "cache_hits": cache_delta["hits"],
                    "cache_misses": cache_delta["misses"],
                    "cache_writes": cache_delta["writes"],
                    "stale_cache_uses": cache_delta["stale_uses"],
                    "query_results": query_results,
                }
            )
            cache_note = (
                f" cache hits={cache_delta['hits']} misses={cache_delta['misses']} stale={cache_delta['stale_uses']}"
                if self.config.cache_enabled
                else " cache disabled"
            )
            diagnostics.append(f"{source}: {len(search_queries)} 个检索式返回 {source_count} 条，用时 {elapsed:.1f}s，状态 {status}.{cache_note}")
        deduped = deduplicate_papers(papers)
        deduped, enrichment_diagnostics = self._enrich_crossref_metadata(deduped)
        diagnostics.extend(enrichment_diagnostics)
        ranked = rank_papers(deduped, topic, search_queries)
        filtered = filter_relevant_papers(ranked, topic, search_queries, self.config.min_relevance)
        if not filtered and ranked:
            diagnostics.append("相关性过滤为空，保留排序最高的少量候选供人工检查。")
            filtered = ranked[: min(len(ranked), self.config.max_papers)]
        diagnostics.append(f"合并去重后 {len(deduped)} 条，相关性过滤后 {len(filtered)} 条。")
        return filtered[: self.config.max_papers], diagnostics

    def _enrich_crossref_metadata(self, papers: list[Paper]) -> tuple[list[Paper], list[str]]:
        if "crossref" not in {source.strip().lower() for source in self.config.sources}:
            return papers, []
        enriched: list[Paper] = []
        diagnostics: list[str] = []
        max_checks = min(6, max(1, self.config.max_papers))
        checked = 0
        improved = 0
        for paper in papers:
            if checked >= max_checks or not _needs_crossref_enrichment(paper):
                enriched.append(paper)
                continue
            checked += 1
            try:
                resolved = self.resolve_crossref_doi(paper.doi)
            except Exception as exc:
                diagnostics.append(f"crossref_enrichment: DOI {paper.doi} 元数据补强失败：{self._safe_error(exc)}")
                enriched.append(paper)
                continue
            if resolved is None:
                enriched.append(paper)
                continue
            merged = deduplicate_papers([paper, resolved])[0]
            if _metadata_signature(merged) != _metadata_signature(paper):
                improved += 1
            enriched.append(merged)
        if checked:
            diagnostics.append(f"crossref_enrichment: 检查 {checked} 条 DOI 薄题录，补强 {improved} 条。")
        return deduplicate_papers(enriched), diagnostics

    def search_semantic_scholar(self, topic: str, limit: int) -> list[Paper]:
        fields = ",".join(
            [
                "title",
                "authors",
                "year",
                "venue",
                "url",
                "abstract",
                "citationCount",
                "externalIds",
            ]
        )
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode(
            {"query": topic, "limit": min(limit, 20), "fields": fields}
        )
        headers = self._headers()
        api_key = self._configured_api_key(self.config.semantic_scholar_api_key, self.config.semantic_scholar_api_key_env)
        if api_key:
            headers["x-api-key"] = api_key
        data = self._json(url, headers=headers)
        papers: list[Paper] = []
        for item in data.get("data", []):
            title = _clean_text(item.get("title"))
            if not title:
                continue
            authors = [_clean_text(author.get("name")) for author in item.get("authors", []) if author.get("name")]
            external_ids = {str(k): str(v) for k, v in (item.get("externalIds") or {}).items() if v}
            doi = external_ids.get("DOI", "")
            papers.append(
                Paper(
                    title=title,
                    authors=authors[:8],
                    year=_safe_int(item.get("year")),
                    venue=_clean_text(item.get("venue")) or "Semantic Scholar",
                    url=_clean_text(item.get("url")) or _doi_url(doi),
                    abstract=_clean_text(item.get("abstract")),
                    relevance=0.84,
                    source="semantic_scholar",
                    sources=["semantic_scholar"],
                    doi=doi,
                    external_ids=external_ids,
                    citation_count=_safe_optional_int(item.get("citationCount")),
                )
            )
        return papers

    def search_openalex(self, topic: str, limit: int) -> list[Paper]:
        params = {
            "search": topic,
            "per-page": str(min(limit, 25)),
            "sort": "relevance_score:desc",
            "select": "id,doi,display_name,authorships,publication_year,primary_location,locations,abstract_inverted_index,cited_by_count,ids,type",
        }
        email = self._configured_contact_email()
        if email:
            params["mailto"] = email
        api_key = self._configured_api_key(self.config.openalex_api_key, self.config.openalex_api_key_env)
        if api_key:
            params["api_key"] = api_key
        data = self._json("https://api.openalex.org/works?" + urlencode(params), headers=self._headers())
        papers: list[Paper] = []
        for item in data.get("results", []):
            title = _clean_text(item.get("display_name"))
            if not title:
                continue
            doi = _normalize_doi(_clean_text(item.get("doi")))
            authors = [
                _clean_text((authorship.get("author") or {}).get("display_name"))
                for authorship in item.get("authorships", [])
            ]
            venue = _openalex_venue(item)
            url = _openalex_url(item, doi)
            openalex_id = _clean_text(item.get("id"))
            external_ids = {k: v for k, v in {"OpenAlex": openalex_id, "DOI": doi}.items() if v}
            papers.append(
                Paper(
                    title=title,
                    authors=[author for author in authors if author][:8],
                    year=_safe_int(item.get("publication_year")),
                    venue=venue or "OpenAlex",
                    url=url,
                    abstract=_openalex_abstract(item.get("abstract_inverted_index")),
                    relevance=0.83,
                    source="openalex",
                    sources=["openalex"],
                    doi=doi,
                    external_ids=external_ids,
                    citation_count=_safe_optional_int(item.get("cited_by_count")),
                )
            )
        return papers

    def search_crossref(self, topic: str, limit: int) -> list[Paper]:
        params = {"query": topic, "rows": min(limit, 20), "select": "DOI,title,author,published-print,published-online,issued,container-title,URL,abstract,score,is-referenced-by-count"}
        email = self._configured_contact_email()
        if email:
            params["mailto"] = email
        data = self._json("https://api.crossref.org/works?" + urlencode(params), headers=self._headers())
        papers: list[Paper] = []
        for item in data.get("message", {}).get("items", []):
            paper = _paper_from_crossref_item(item)
            if paper is not None:
                papers.append(paper)
        return papers

    def resolve_crossref_doi(self, doi: str) -> Paper | None:
        normalized = _normalize_doi(doi)
        if not normalized:
            return None
        data = self._json("https://api.crossref.org/works/" + quote(normalized, safe=""), headers=self._headers())
        item = data.get("message") if isinstance(data.get("message"), dict) else {}
        return _paper_from_crossref_item(item)

    def resolve_doi_metadata(self, doi: str) -> Paper | None:
        normalized = _normalize_doi(doi)
        if not normalized:
            return None
        try:
            return self.resolve_crossref_doi(normalized)
        except Exception:
            pass
        data = self._json(
            "https://doi.org/" + quote(normalized, safe="/"),
            headers={**self._headers(), "Accept": "application/vnd.citationstyles.csl+json"},
        )
        return _paper_from_csl_item(data, normalized)

    def search_arxiv(self, topic: str, limit: int) -> list[Paper]:
        query = quote(" ".join(_query_terms(topic)[:8]) or topic)
        url = f"https://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={min(limit, 20)}&sortBy=relevance&sortOrder=descending"
        xml = self._bytes(url, headers=self._headers()).decode("utf-8", errors="replace")
        root = ET.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        papers: list[Paper] = []
        for entry in root.findall("atom:entry", ns):
            title = _clean_text(_element_text(entry, "atom:title", ns))
            if not title:
                continue
            authors = [_clean_text(_element_text(author, "atom:name", ns)) for author in entry.findall("atom:author", ns)]
            year = _safe_int((_element_text(entry, "atom:published", ns) or "")[:4])
            arxiv_id = (_element_text(entry, "atom:id", ns) or "").rsplit("/", 1)[-1]
            doi = _clean_text(_element_text(entry, "arxiv:doi", ns))
            papers.append(
                Paper(
                    title=title,
                    authors=[author for author in authors if author][:8],
                    year=year,
                    venue="arXiv",
                    url=_clean_text(_element_text(entry, "atom:id", ns)) or _doi_url(doi),
                    abstract=_clean_text(_element_text(entry, "atom:summary", ns)),
                    relevance=0.82,
                    source="arxiv",
                    sources=["arxiv"],
                    doi=doi,
                    external_ids={k: v for k, v in {"arXiv": arxiv_id, "DOI": doi}.items() if v},
                    citation_count=None,
                )
            )
        return papers

    def search_pubmed(self, topic: str, limit: int) -> list[Paper]:
        params = {
            "db": "pubmed",
            "term": topic,
            "retmax": str(min(limit, 20)),
            "retmode": "json",
            "sort": "relevance",
            "tool": "research-agent",
        }
        email = self._configured_contact_email()
        if email:
            params["email"] = email
        ids_data = self._json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode(params), headers=self._headers())
        ids = ids_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        summary_params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
            "tool": "research-agent",
        }
        if email:
            summary_params["email"] = email
        data = self._json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode(summary_params), headers=self._headers())
        result = data.get("result", {})
        papers: list[Paper] = []
        for pmid in ids:
            item = result.get(str(pmid), {})
            title = _clean_text(item.get("title"))
            if not title:
                continue
            authors = [_clean_text(author.get("name")) for author in item.get("authors", []) if author.get("name")]
            article_ids = item.get("articleids", []) or []
            doi = ""
            for article_id in article_ids:
                if article_id.get("idtype") == "doi":
                    doi = _clean_text(article_id.get("value"))
                    break
            papers.append(
                Paper(
                    title=title,
                    authors=authors[:8],
                    year=_safe_int(str(item.get("pubdate", ""))[:4]),
                    venue=_clean_text(item.get("source")) or "PubMed",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    abstract="PubMed summary metadata returned without abstract in this lightweight search path.",
                    relevance=0.80,
                    source="pubmed",
                    sources=["pubmed"],
                    doi=doi,
                    external_ids={k: v for k, v in {"PMID": str(pmid), "DOI": doi}.items() if v},
                    citation_count=None,
                )
            )
        return papers

    def _configured_api_key(self, value: str, env_name: str) -> str:
        for candidate in [value, os.environ.get(env_name, "")]:
            text = str(candidate or "").strip()
            if text and not placeholder_secret(text):
                return text
        return ""

    def _configured_contact_email(self) -> str:
        for candidate in [self.config.contact_email, os.environ.get(self.config.contact_email_env, "")]:
            text = str(candidate or "").strip()
            if text and valid_contact_email(text):
                return text
        return ""

    def _safe_error(self, exc: Exception | str) -> str:
        text = str(exc)
        for secret in [
            self.config.semantic_scholar_api_key,
            self.config.openalex_api_key,
            self.config.contact_email,
            os.environ.get(self.config.semantic_scholar_api_key_env, ""),
            os.environ.get(self.config.openalex_api_key_env, ""),
            os.environ.get(self.config.contact_email_env, ""),
        ]:
            value = str(secret or "").strip()
            if value:
                text = text.replace(value, "***")
        text = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1***", text)
        text = re.sub(r"(?i)(mailto=)[^&\s]+", r"\1***", text)
        text = re.sub(r"(?i)(email=)[^&\s]+", r"\1***", text)
        text = re.sub(r"(?i)(x-api-key['\"]?\s*[:=]\s*)[^,\s}]+", r"\1***", text)
        return text

    def _json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        raw = self._bytes(url, headers)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise LiteratureSourceError(f"无法解析 JSON: {exc}") from exc

    def _bytes(self, url: str, headers: dict[str, str]) -> bytes:
        cached = self._read_cache(url, allow_stale=False)
        if cached is not None:
            self._cache_stats["hits"] += 1
            return cached
        if self.config.cache_enabled:
            self._cache_stats["misses"] += 1
        try:
            data = self._network_bytes(url, headers)
        except urllib.error.HTTPError as exc:
            detail = self._safe_error(exc.read().decode("utf-8", errors="replace"))[:500]
            stale = self._read_cache(url, allow_stale=True)
            if stale is not None and exc.code in {429, 500, 502, 503, 504}:
                self._cache_stats["stale_uses"] += 1
                return stale
            raise LiteratureSourceError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            stale = self._read_cache(url, allow_stale=True)
            if stale is not None:
                self._cache_stats["stale_uses"] += 1
                return stale
            raise LiteratureSourceError(self._safe_error(str(exc.reason))) from exc
        self._write_cache(url, data)
        return data

    def _network_bytes(self, url: str, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": USER_AGENT, "Accept": "application/json"}

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        root = Path(self.config.cache_dir)
        return root / f"{key}.body", root / f"{key}.json"

    def _read_cache(self, url: str, allow_stale: bool) -> bytes | None:
        if not self.config.cache_enabled:
            return None
        body_path, meta_path = self._cache_paths(url)
        if not body_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created_at = float(meta.get("created_at", 0.0))
            if not allow_stale and time.time() - created_at > max(1, self.config.cache_ttl_seconds):
                return None
            return body_path.read_bytes()
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache(self, url: str, data: bytes) -> None:
        if not self.config.cache_enabled:
            return
        body_path, meta_path = self._cache_paths(url)
        try:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_bytes(data)
            meta_path.write_text(json.dumps({"url": url, "created_at": time.time()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._cache_stats["writes"] += 1
        except OSError:
            return


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    by_key: dict[str, Paper] = {}
    aliases: dict[str, str] = {}
    title_aliases: dict[str, str] = {}
    order: list[str] = []
    for paper in papers:
        key = _dedup_key(paper)
        if not key:
            continue
        title_key = _title_dedup_key(paper)
        canonical_key = aliases.get(key)
        if canonical_key is None and title_key:
            candidate_key = title_aliases.get(title_key)
            if candidate_key and _can_merge_by_title(by_key[candidate_key], paper):
                canonical_key = candidate_key
        if canonical_key is None:
            canonical_key = key
            by_key[canonical_key] = _normalize_paper_sources(paper)
            aliases[key] = canonical_key
            if title_key:
                title_aliases.setdefault(title_key, canonical_key)
            order.append(canonical_key)
            continue
        by_key[canonical_key] = _merge_papers(by_key[canonical_key], paper)
        aliases[key] = canonical_key
        merged_key = _dedup_key(by_key[canonical_key])
        if merged_key:
            aliases[merged_key] = canonical_key
        if title_key:
            title_aliases.setdefault(title_key, canonical_key)
    return [by_key[key] for key in order]


def _cache_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in {"hits", "misses", "writes", "stale_uses"}}


def rank_papers(papers: list[Paper], topic: str, queries: list[str] | None = None) -> list[Paper]:
    terms = set(_query_terms(" ".join([topic] + (queries or []))))

    def score(paper: Paper) -> float:
        return _relevance_score(paper, terms)

    return sorted(papers, key=score, reverse=True)


def filter_relevant_papers(
    papers: list[Paper], topic: str, queries: list[str] | None = None, min_relevance: float = 0.24
) -> list[Paper]:
    terms = set(_query_terms(" ".join([topic] + (queries or []))))
    filtered: list[Paper] = []
    for paper in papers:
        score = _relevance_score(paper, terms)
        has_metadata = bool(paper.abstract and len(paper.abstract) > 60) or paper.source in {"semantic_scholar", "openalex", "arxiv", "pubmed"}
        if score >= min_relevance and has_metadata:
            filtered.append(replace(paper, relevance=round(score, 4)))
    return filtered


def _relevance_score(paper: Paper, terms: set[str]) -> float:
    text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
    title = paper.title.lower()
    matched = {term for term in terms if term in text}
    title_matches = {term for term in terms if term in title}
    lexical = len(matched) / max(len(terms), 1) if terms else 0.0
    title_bonus = min(0.2, 0.05 * len(title_matches))
    abstract_bonus = 0.08 if paper.abstract and len(paper.abstract) > 100 else -0.06
    recency = min(max(paper.year - 2018, 0), 8) / 100.0
    citations = min(paper.citation_count or 0, 500) / 5000.0
    source_bonus = {"semantic_scholar": 0.08, "openalex": 0.07, "arxiv": 0.08, "pubmed": 0.06, "crossref": -0.05}.get(paper.source, 0.0)
    multi_source = 0.04 * max(0, len(set(paper.sources or [paper.source])) - 1)
    return paper.relevance * 0.38 + lexical * 0.52 + title_bonus + abstract_bonus + recency + citations + source_bonus + multi_source


def _normalize_queries(queries: list[str], topic: str, max_queries: int) -> list[str]:
    cleaned: list[str] = []
    for query in queries + _fallback_queries(topic) + [topic]:
        value = re.sub(r"\s+", " ", str(query)).strip().strip('"')
        if not value or value in cleaned:
            continue
        cleaned.append(value)
        if len(cleaned) >= max(1, max_queries):
            break
    return cleaned or [topic]


def _fallback_queries(topic: str) -> list[str]:
    lower = topic.lower()
    if "机械臂" in topic or "robot" in lower or "manipulator" in lower:
        return [
            "robot manipulator motion planning",
            "robot arm path planning obstacle avoidance",
            "manipulator trajectory planning sampling-based planning",
        ]
    return []


def build_evidence_table(papers: list[Paper]) -> list[dict[str, str | int | float | None]]:
    rows: list[dict[str, str | int | float | None]] = []
    for paper in papers:
        sources = ", ".join(paper.sources or [paper.source])
        rows.append(
            {
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "sources": sources,
                "doi": paper.doi,
                "citations": paper.citation_count,
                "relevance": round(paper.relevance, 3),
                "evidence_note": paper.evidence_note or _evidence_note(paper),
            }
        )
    return rows


def annotate_evidence(papers: list[Paper], topic: str) -> list[Paper]:
    return [
        replace(paper, sources=paper.sources or [paper.source], evidence_note=_evidence_note(paper, topic))
        for paper in papers
    ]


def _merge_papers(existing: Paper, incoming: Paper) -> Paper:
    sources = sorted(set((existing.sources or [existing.source]) + (incoming.sources or [incoming.source])))
    external_ids = {**incoming.external_ids, **existing.external_ids}
    doi = existing.doi or incoming.doi
    existing_is_manual = "manual_seed" in set(existing.sources or [existing.source])
    incoming_is_manual = "manual_seed" in set(incoming.sources or [incoming.source])
    title = incoming.title if existing_is_manual and not incoming_is_manual and incoming.title else existing.title
    abstract = existing.abstract if len(existing.abstract) >= len(incoming.abstract) else incoming.abstract
    if existing_is_manual and not incoming_is_manual:
        authors = incoming.authors or existing.authors
        year = incoming.year or existing.year
        url = _best_url(existing.url, incoming.url)
        venue = _best_venue(existing, incoming)
    else:
        authors = existing.authors if len(existing.authors) >= len(incoming.authors) else incoming.authors
        year = existing.year or incoming.year
        url = _best_url(existing.url, incoming.url)
        venue = _best_venue(existing, incoming)
    citation_count = max(existing.citation_count or 0, incoming.citation_count or 0) or None
    return replace(
        existing,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        url=url,
        abstract=abstract,
        relevance=min(1.0, max(existing.relevance, incoming.relevance) + min(0.08, 0.03 * (len(sources) - 1))),
        source=_primary_source(sources),
        sources=sources,
        doi=doi,
        external_ids=external_ids,
        citation_count=citation_count,
    )


def _normalize_paper_sources(paper: Paper) -> Paper:
    sources = paper.sources or [paper.source]
    clean_sources = sorted(set(source for source in sources if source))
    return replace(paper, source=_primary_source(clean_sources or [paper.source]), sources=clean_sources)


def _dedup_key(paper: Paper) -> str:
    if paper.doi:
        return "doi:" + paper.doi.lower().strip()
    arxiv_id = paper.external_ids.get("arXiv") or paper.external_ids.get("ARXIV")
    if arxiv_id:
        return "arxiv:" + arxiv_id.lower().strip()
    pmid = paper.external_ids.get("PMID")
    if pmid:
        return "pmid:" + pmid.lower().strip()
    title_key = _normalize_title(paper.title)
    return "title:" + title_key if title_key else ""


def _title_dedup_key(paper: Paper) -> str:
    title_key = _normalize_title(paper.title)
    return "title:" + title_key if title_key else ""


def _can_merge_by_title(existing: Paper, incoming: Paper) -> bool:
    if not _normalize_title(existing.title) or _normalize_title(existing.title) != _normalize_title(incoming.title):
        return False
    if existing.doi and incoming.doi and existing.doi.lower().strip() != incoming.doi.lower().strip():
        return False
    return True


def _needs_crossref_enrichment(paper: Paper) -> bool:
    if not paper.doi:
        return False
    if paper.source == "crossref" and "crossref" in set(paper.sources or [paper.source]):
        return False
    if not paper.authors or not paper.year:
        return True
    if _is_generic_venue(paper.venue, paper.source):
        return True
    if len(paper.abstract or "") < 80:
        return True
    return False


def _metadata_signature(paper: Paper) -> tuple[Any, ...]:
    return (
        tuple(paper.authors),
        paper.year,
        paper.venue,
        paper.url,
        len(paper.abstract or ""),
        paper.citation_count,
        tuple(paper.sources or [paper.source]),
    )


def _primary_source(sources: list[str]) -> str:
    priority = {
        "semantic_scholar": 90,
        "openalex": 85,
        "arxiv": 80,
        "pubmed": 75,
        "offline": 65,
        "manual_seed": 60,
        "crossref": 45,
    }
    clean = [source for source in sources if source]
    if not clean:
        return ""
    return max(clean, key=lambda source: (priority.get(source, 50), -clean.index(source)))


def _best_url(existing: str, incoming: str) -> str:
    if existing and incoming and _is_doi_url(existing) and not _is_doi_url(incoming):
        return incoming
    return existing or incoming


def _best_venue(existing: Paper, incoming: Paper) -> str:
    if _is_generic_venue(existing.venue, existing.source) and not _is_generic_venue(incoming.venue, incoming.source):
        return incoming.venue
    return existing.venue or incoming.venue


def _is_doi_url(value: str) -> bool:
    return bool(re.match(r"https?://(?:dx\.)?doi\.org/", value.strip(), flags=re.I))


def _is_generic_venue(venue: str, source: str) -> bool:
    value = venue.strip().lower()
    return not value or value == source.strip().lower() or value in {"crossref", "semantic scholar", "openalex", "pubmed", "manual seed"}


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:180]


def _query_terms(topic: str) -> list[str]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", topic.lower())
    stop = {"the", "and", "for", "with", "how", "what", "are", "from", "into", "agent", "agents"}
    deduped: list[str] = []
    for term in terms:
        normalized = term.replace("-", "_")
        if normalized in stop or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


def _evidence_note(paper: Paper, topic: str = "") -> str:
    title = paper.title.lower()
    abstract = paper.abstract.lower()
    if any(term in title or term in abstract for term in ["survey", "review", "综述"]):
        return "综述/回顾类文献，可用于建立背景和研究空白。"
    if any(term in title or term in abstract for term in ["agent", "autonomous", "automated", "tool"]):
        return "涉及 agent、工具调用或自动化流程，是平台架构的直接证据。"
    if any(term in title or term in abstract for term in ["benchmark", "evaluation", "dataset", "experiment"]):
        return "包含评估、数据集或实验线索，适合转化为 benchmark。"
    if topic:
        return "与课题关键词相关，可作为候选背景文献进一步精读。"
    return "候选证据，需要人工精读后确认可引用结论。"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item)
    text = unescape(str(value))
    text = _strip_tags(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return _clean_text(value[0]) if value else ""
    return _clean_text(value)


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def _normalize_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.strip()


def _paper_from_crossref_item(item: dict[str, Any]) -> Paper | None:
    title = _first_text(item.get("title"))
    if not title:
        return None
    doi = _clean_text(item.get("DOI"))
    authors = [_format_crossref_author(author) for author in item.get("author", [])]
    year = _crossref_year(item)
    abstract = _strip_tags(_clean_text(item.get("abstract")))
    venue = _first_text(item.get("container-title")) or "Crossref"
    score = _safe_float(item.get("score"), 0.0)
    return Paper(
        title=title,
        authors=[author for author in authors if author][:8],
        year=year,
        venue=venue,
        url=_clean_text(item.get("URL")) or _doi_url(doi),
        abstract=abstract,
        relevance=min(0.78, 0.46 + score / 220.0),
        source="crossref",
        sources=["crossref"],
        doi=doi,
        external_ids={"DOI": doi} if doi else {},
        citation_count=_safe_optional_int(item.get("is-referenced-by-count")),
    )


def _paper_from_csl_item(item: dict[str, Any], doi: str) -> Paper | None:
    title = _clean_text(item.get("title"))
    if not title:
        return None
    authors = [_format_csl_author(author) for author in item.get("author", []) if isinstance(author, dict)]
    issued = item.get("issued") if isinstance(item.get("issued"), dict) else {}
    date_parts = issued.get("date-parts") if isinstance(issued.get("date-parts"), list) else []
    first_part = date_parts[0] if date_parts and isinstance(date_parts[0], list) else []
    year = _safe_int(first_part[0] if first_part else 0)
    venue = _clean_text(item.get("container-title")) or _clean_text(item.get("publisher")) or _clean_text(item.get("type")) or "DOI"
    abstract = _clean_text(item.get("abstract")) or _clean_text(item.get("note")) or f"DOI.org metadata for {title}."
    normalized = _normalize_doi(_clean_text(item.get("DOI")) or doi)
    return Paper(
        title=title,
        authors=[author for author in authors if author][:8],
        year=year,
        venue=venue,
        url=_clean_text(item.get("URL")) or _clean_text(item.get("id")) or _doi_url(normalized),
        abstract=abstract,
        relevance=0.78,
        source="doi",
        sources=["doi"],
        doi=normalized,
        external_ids={"DOI": normalized} if normalized else {},
    )


def _openalex_abstract(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            index = _safe_int(position)
            if index >= 0:
                positioned.append((index, str(word)))
    return _clean_text(" ".join(word for _, word in sorted(positioned)))


def _openalex_venue(item: dict[str, Any]) -> str:
    primary = item.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = _clean_text(source.get("display_name"))
    if venue:
        return venue
    for location in item.get("locations", []) or []:
        source = (location or {}).get("source") or {}
        venue = _clean_text(source.get("display_name"))
        if venue:
            return venue
    return _clean_text(item.get("type")) or "OpenAlex"


def _openalex_url(item: dict[str, Any], doi: str) -> str:
    primary = item.get("primary_location") or {}
    url = _clean_text(primary.get("landing_page_url") or primary.get("pdf_url"))
    if url:
        return url
    ids = item.get("ids") or {}
    return _clean_text(ids.get("openalex")) or _doi_url(doi)


def _format_crossref_author(author: dict[str, Any]) -> str:
    given = _clean_text(author.get("given"))
    family = _clean_text(author.get("family"))
    return " ".join(part for part in [given, family] if part)


def _format_csl_author(author: dict[str, Any]) -> str:
    literal = _clean_text(author.get("literal"))
    if literal:
        return literal
    given = _clean_text(author.get("given"))
    family = _clean_text(author.get("family"))
    return " ".join(part for part in [given, family] if part)


def _crossref_year(item: dict[str, Any]) -> int:
    for key in ["published-print", "published-online", "issued"]:
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            return _safe_int(parts[0][0])
    return 0


def _element_text(element: ET.Element, path: str, ns: dict[str, str]) -> str:
    child = element.find(path, ns)
    return child.text if child is not None and child.text else ""
