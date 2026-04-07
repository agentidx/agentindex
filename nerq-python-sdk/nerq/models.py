"""Nerq SDK data models."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _get(d: Dict, key: str, default=None):
    return d.get(key, default)


@dataclass
class PreflightResult:
    """Result of a preflight trust check on an AI agent."""
    target: str
    found: bool
    trust_score: Optional[float]
    trust_grade: Optional[str]
    recommendation: str       # PROCEED / CAUTION / DENY
    agent_name: Optional[str]
    source: Optional[str]
    category: Optional[str]
    license: Optional[str]
    stars: Optional[int]
    downloads: Optional[int]
    cve_count: Optional[int]
    alternatives: List[Dict]
    components: Optional[Dict]
    raw: Dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict) -> "PreflightResult":
        return cls(
            target=_get(d, "target", ""),
            found=bool(_get(d, "found", False)),
            trust_score=_get(d, "trust_score"),
            trust_grade=_get(d, "trust_grade"),
            recommendation=_get(d, "recommendation", "UNKNOWN"),
            agent_name=_get(d, "agent_name") or _get(d, "name"),
            source=_get(d, "source"),
            category=_get(d, "category"),
            license=_get(d, "license"),
            stars=_get(d, "stars"),
            downloads=_get(d, "downloads"),
            cve_count=_get(d, "cve_count"),
            alternatives=_get(d, "alternatives") or [],
            components=_get(d, "trust_components") or _get(d, "components"),
            raw=d,
        )

    def is_safe(self) -> bool:
        return self.recommendation == "PROCEED"

    def should_deny(self) -> bool:
        return self.recommendation == "DENY"


@dataclass
class BatchPreflightResult:
    """Result of a batch preflight check."""
    results: Dict[str, PreflightResult]
    not_found: List[str]

    def items(self):
        return self.results.items()

    def __getitem__(self, target: str) -> PreflightResult:
        return self.results[target]

    def safe_agents(self) -> List[str]:
        return [t for t, r in self.results.items() if r.is_safe()]

    def denied_agents(self) -> List[str]:
        return [t for t, r in self.results.items() if r.should_deny()]


@dataclass
class AgentSearchResult:
    """A single agent from search results."""
    id: str
    name: str
    description: Optional[str]
    source: Optional[str]
    trust_score: Optional[float]
    trust_grade: Optional[str]
    stars: Optional[int]
    downloads: Optional[int]
    category: Optional[str]
    source_url: Optional[str]
    raw: Dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict) -> "AgentSearchResult":
        return cls(
            id=str(_get(d, "id", "")),
            name=_get(d, "name", ""),
            description=_get(d, "description"),
            source=_get(d, "source"),
            trust_score=_get(d, "trust_score"),
            trust_grade=_get(d, "trust_grade"),
            stars=_get(d, "stars"),
            downloads=_get(d, "downloads"),
            category=_get(d, "category"),
            source_url=_get(d, "source_url"),
            raw=d,
        )


@dataclass
class CommerceVerdict:
    """Result of a commerce trust verification."""
    verdict: str              # approve / review / reject
    agent_score: Optional[float]
    counterparty_score: Optional[float]
    risk_level: str
    reason: str
    raw: Dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict) -> "CommerceVerdict":
        return cls(
            verdict=_get(d, "verdict", "reject"),
            agent_score=_get(d, "agent_score"),
            counterparty_score=_get(d, "counterparty_score"),
            risk_level=_get(d, "risk_level", "unknown"),
            reason=_get(d, "reason", ""),
            raw=d,
        )

    def is_approved(self) -> bool:
        return self.verdict == "approve"

    def needs_review(self) -> bool:
        return self.verdict == "review"
