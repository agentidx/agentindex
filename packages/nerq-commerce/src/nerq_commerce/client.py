"""Nerq Commerce Trust — Verify AI agents before transactions."""
import time
from dataclasses import dataclass
from typing import Optional
import requests

API_BASE = "https://nerq.ai"
ENDPOINT = "/v1/commerce/verify"
BATCH_ENDPOINT = "/v1/commerce/verify/batch"


@dataclass
class VerificationResult:
    verdict: str  # approve, review, reject
    agent_trust_score: Optional[float]
    counterparty_trust_score: Optional[float]
    risk_factors: list
    recommended_action: str
    threshold_applied: int
    response_time_ms: float

    @property
    def approved(self) -> bool:
        return self.verdict == "approve"

    def __bool__(self) -> bool:
        return self.approved


def verify_transaction(
    agent_id: str,
    counterparty_id: str,
    transaction_type: str = "purchase",
    amount_range: str = "medium",
    api_base: str = API_BASE,
    timeout: int = 10,
) -> VerificationResult:
    """Verify a transaction between two agents.

    Args:
        agent_id: Name of the agent initiating the transaction.
        counterparty_id: Name of the counterparty agent.
        transaction_type: One of purchase, delegation, data_exchange, payment.
        amount_range: Risk level — low, medium, high, critical.
        api_base: Nerq API base URL.
        timeout: Request timeout in seconds.

    Returns:
        VerificationResult with verdict, scores, and risk factors.
    """
    resp = requests.post(
        f"{api_base}{ENDPOINT}",
        json={
            "agent_id": agent_id,
            "counterparty_id": counterparty_id,
            "transaction_type": transaction_type,
            "amount_range": amount_range,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return VerificationResult(
        verdict=data["verdict"],
        agent_trust_score=data.get("agent_trust_score"),
        counterparty_trust_score=data.get("counterparty_trust_score"),
        risk_factors=data.get("risk_factors", []),
        recommended_action=data.get("recommended_action", ""),
        threshold_applied=data.get("threshold_applied", 0),
        response_time_ms=data.get("response_time_ms", 0),
    )


class CommerceGate:
    """Configurable commerce trust gate with caching and auto-retry.

    Usage:
        gate = CommerceGate(default_threshold=70)
        result = gate.verify("my-agent", "vendor-agent", "purchase")
        if result.approved:
            execute_transaction()
    """

    def __init__(
        self,
        default_threshold: int = 70,
        api_base: str = API_BASE,
        cache_ttl: int = 300,
        max_retries: int = 2,
        timeout: int = 10,
    ):
        self.default_threshold = default_threshold
        self.api_base = api_base
        self.cache_ttl = cache_ttl
        self.max_retries = max_retries
        self.timeout = timeout
        self._cache: dict = {}

    def verify(
        self,
        agent_id: str,
        counterparty_id: str,
        transaction_type: str = "purchase",
        amount_range: str = "medium",
    ) -> VerificationResult:
        """Verify a transaction with caching and retry."""
        cache_key = f"{agent_id}:{counterparty_id}:{transaction_type}:{amount_range}"
        now = time.time()

        if cache_key in self._cache:
            cached, ts = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return cached

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = verify_transaction(
                    agent_id=agent_id,
                    counterparty_id=counterparty_id,
                    transaction_type=transaction_type,
                    amount_range=amount_range,
                    api_base=self.api_base,
                    timeout=self.timeout,
                )
                self._cache[cache_key] = (result, now)
                return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        # All retries failed — return reject
        return VerificationResult(
            verdict="reject",
            agent_trust_score=None,
            counterparty_trust_score=None,
            risk_factors=[f"Verification service unavailable: {last_error}"],
            recommended_action="Transaction rejected — unable to verify trust scores.",
            threshold_applied=self.default_threshold,
            response_time_ms=0,
        )

    def verify_batch(
        self,
        transactions: list[dict],
    ) -> list[VerificationResult]:
        """Verify multiple transactions in one call."""
        resp = requests.post(
            f"{self.api_base}{BATCH_ENDPOINT}",
            json={"transactions": transactions},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            VerificationResult(
                verdict=r["verdict"],
                agent_trust_score=r.get("agent_trust_score"),
                counterparty_trust_score=r.get("counterparty_trust_score"),
                risk_factors=r.get("risk_factors", []),
                recommended_action=r.get("recommended_action", ""),
                threshold_applied=r.get("threshold_applied", 0),
                response_time_ms=r.get("response_time_ms", 0),
            )
            for r in data.get("results", [])
        ]
