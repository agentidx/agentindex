"""
NerqClient — Python client for the Nerq Trust API.

Nerq indexes 204K+ AI agents and MCP servers with Trust Scores.
Use this client for preflight trust checks, batch verification,
agent search, and commerce trust gating.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import (
    PreflightResult, BatchPreflightResult,
    AgentSearchResult, CommerceVerdict,
)
from .exceptions import (
    NerqError, NerqNotFoundError, NerqRateLimitError,
    NerqAuthError, NerqTimeoutError,
)

DEFAULT_BASE_URL = "https://nerq.ai"
DEFAULT_TIMEOUT = 10
__version__ = "1.0.0"


class NerqClient:
    """
    Nerq Trust API client.

    Parameters
    ----------
    api_key : str, optional
        API key for higher rate limits. Free tier (100 req/hour) works without a key.
    base_url : str, optional
        Override API base URL.
    timeout : int, optional
        Request timeout in seconds (default: 10).
    retries : int, optional
        Retry attempts on transient errors (default: 3).

    Examples
    --------
    Preflight check:
        >>> from nerq import NerqClient
        >>> client = NerqClient()
        >>> result = client.preflight("langchain-ai/langchain")
        >>> print(result.trust_score, result.recommendation)

    Batch check:
        >>> results = client.preflight_batch(["langchain", "crewai", "autogen"])
        >>> for name, r in results.items():
        ...     print(name, r.trust_grade, r.recommendation)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = self._build_session(retries)

    def _build_session(self, retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _headers(self) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "User-Agent": f"nerq-python/{__version__}",
        }
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(
                url, headers=self._headers(), params=params, timeout=self.timeout
            )
        except requests.Timeout:
            raise NerqTimeoutError(f"Request timed out after {self.timeout}s: {url}")
        return self._handle(resp)

    def _post(self, path: str, json_data: Dict) -> Dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.post(
                url, headers=self._headers(), json=json_data, timeout=self.timeout
            )
        except requests.Timeout:
            raise NerqTimeoutError(f"Request timed out after {self.timeout}s: {url}")
        return self._handle(resp)

    def _handle(self, resp: requests.Response) -> Dict:
        if resp.status_code == 404:
            raise NerqNotFoundError(resp.json().get("detail", "Not found"))
        if resp.status_code == 401:
            raise NerqAuthError("Invalid or missing API key")
        if resp.status_code == 429:
            raise NerqRateLimitError("Rate limit exceeded — 100 requests/hour on free tier")
        if not resp.ok:
            raise NerqError(f"API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ── PREFLIGHT ─────────────────────────────────────────────────────────────

    def preflight(self, target: str, caller: Optional[str] = None) -> PreflightResult:
        """
        Preflight trust check for an AI agent or MCP server.

        Parameters
        ----------
        target : str
            Agent name, GitHub repo (owner/repo), or package name.
        caller : str, optional
            Identifier of the calling agent (for audit trail).

        Returns
        -------
        PreflightResult
            Trust score, grade, recommendation (PROCEED/CAUTION/DENY),
            CVE count, license, alternatives.

        Example
        -------
        >>> r = client.preflight("langchain-ai/langchain")
        >>> if r.is_safe():
        ...     print("Safe to use")
        >>> else:
        ...     print(f"Caution: {r.trust_grade}, alternatives: {r.alternatives}")
        """
        params = {"target": target}
        if caller:
            params["caller"] = caller
        data = self._get("/v1/preflight", params=params)
        return PreflightResult.from_dict(data)

    def preflight_batch(self, targets: List[str], caller: Optional[str] = None) -> BatchPreflightResult:
        """
        Batch preflight check for up to 50 agents.

        Parameters
        ----------
        targets : list of str
            Agent names or repo identifiers (max 50).
        caller : str, optional
            Identifier of the calling agent.

        Returns
        -------
        BatchPreflightResult
            .results → dict[target, PreflightResult]
            .not_found → list of targets not in index

        Example
        -------
        >>> batch = client.preflight_batch(["langchain", "crewai", "autogen"])
        >>> for name, r in batch.items():
        ...     print(f"{name}: {r.trust_grade} ({r.recommendation})")
        >>> print("Not found:", batch.not_found)
        """
        if len(targets) > 50:
            raise ValueError("preflight_batch accepts max 50 targets")
        payload: Dict[str, Any] = {"targets": targets}
        if caller:
            payload["caller"] = caller
        data = self._post("/v1/preflight/batch", payload)
        results = {}
        for target, info in data.get("results", {}).items():
            results[target] = PreflightResult.from_dict(info)
        return BatchPreflightResult(
            results=results,
            not_found=data.get("not_found", []),
        )

    # ── SEARCH ────────────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> List[AgentSearchResult]:
        """
        Search the Nerq agent index.

        Parameters
        ----------
        query : str
            Search query (agent name, category, framework, etc.).
        limit : int
            Max results (default 20, max 100).

        Returns
        -------
        list of AgentSearchResult

        Example
        -------
        >>> agents = client.search("code review", limit=5)
        >>> for a in agents:
        ...     print(a.name, a.trust_score)
        """
        data = self._get("/v1/check", params={"q": query, "limit": limit})
        items = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [AgentSearchResult.from_dict(a) for a in items]
        return []

    # ── COMMERCE ──────────────────────────────────────────────────────────────

    def commerce_verify(
        self,
        agent_id: str,
        counterparty_id: str,
        transaction_type: str = "interaction",
        amount_range: str = "low",
    ) -> CommerceVerdict:
        """
        Commerce trust verification — verify trust before agent transactions.

        Parameters
        ----------
        agent_id : str
            The initiating agent identifier.
        counterparty_id : str
            The counterparty agent identifier.
        transaction_type : str
            Type: 'interaction', 'payment', 'data_exchange', 'api_call'.
        amount_range : str
            Risk tier: 'low', 'medium', 'high'.

        Returns
        -------
        CommerceVerdict
            verdict (approve/review/reject), scores, risk level.

        Example
        -------
        >>> v = client.commerce_verify("my-agent", "seller-agent", "payment", "high")
        >>> if v.is_approved():
        ...     proceed_with_payment()
        """
        data = self._post("/v1/commerce/verify", {
            "agent_id": agent_id,
            "counterparty_id": counterparty_id,
            "transaction_type": transaction_type,
            "amount_range": amount_range,
        })
        return CommerceVerdict.from_dict(data)

    # ── CONTEXT MANAGER ──────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    def close(self):
        self._session.close()
