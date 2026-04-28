"""Smoke-test post-merge: 8 base + 5 localized + 10 sacred-bytes."""
from __future__ import annotations

import random
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable


BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class ProbeResult:
    url: str
    status: int
    ms: float
    error: str | None = None
    body_excerpt: str = ""


@dataclass
class SmokeTestResult:
    base: list[ProbeResult] = field(default_factory=list)
    localized: list[ProbeResult] = field(default_factory=list)
    sacred_bytes: list[ProbeResult] = field(default_factory=list)
    sacred_bytes_pass: int = 0
    sacred_bytes_fail: int = 0

    @property
    def passed(self) -> bool:
        # All base + all localized must be 200; sacred-bytes ≥80% pass
        if any(p.status != 200 for p in self.base):
            return False
        if any(p.status != 200 for p in self.localized):
            return False
        total_sb = self.sacred_bytes_pass + self.sacred_bytes_fail
        if total_sb > 0 and self.sacred_bytes_pass / total_sb < 0.80:
            return False
        return True

    def summary(self) -> str:
        base_ok = sum(1 for p in self.base if p.status == 200)
        loc_ok = sum(1 for p in self.localized if p.status == 200)
        sb_ok = self.sacred_bytes_pass
        sb_total = sb_ok + self.sacred_bytes_fail
        return (
            f"base={base_ok}/{len(self.base)} "
            f"localized={loc_ok}/{len(self.localized)} "
            f"sacred-bytes={sb_ok}/{sb_total}"
        )


BASE_PATHS = [
    "/safe/react",
    "/compare/react-vs-vue",
    "/rating/react.json",
    "/signals/react.json",
    "/dependencies/react.json",
    "/dimensions/react.json",
    "/model/react",
    "/v1/agent/stats",
]

LOCALIZED_PATHS = [
    "/sv/safe/numpy",
    "/de/safe/lodash",
    "/es/safe/express",
    "/ja/safe/django",
    "/ru/safe/flask",
]

SACRED_BYTES_TOP_SLUGS = [
    "react", "numpy", "express", "django", "flask",
    "lodash", "openai", "stripe", "canva", "nordvpn",
]


def _probe(path: str, timeout: float = DEFAULT_TIMEOUT, want_body: bool = False) -> ProbeResult:
    url = f"{BASE_URL}{path}"
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read() if want_body else b""
            return ProbeResult(
                url=path,
                status=r.status,
                ms=(time.time() - t0) * 1000,
                body_excerpt=body.decode("utf-8", errors="ignore")[:5000] if want_body else "",
            )
    except urllib.error.HTTPError as e:
        return ProbeResult(url=path, status=e.code, ms=(time.time() - t0) * 1000, error=str(e))
    except Exception as e:
        return ProbeResult(url=path, status=0, ms=(time.time() - t0) * 1000, error=str(e))


def check_sacred_bytes(slug: str) -> ProbeResult:
    """Verify pplx-verdict, ai-summary, FAQPage JSON-LD intakta."""
    p = _probe(f"/safe/{slug}", want_body=True)
    if p.status != 200:
        return p

    body = p.body_excerpt
    has_pplx = "pplx-verdict" in body
    has_ai_summary = "ai-summary" in body or "ai_summary" in body
    has_faq = re.search(r'"@type"\s*:\s*"FAQPage"', body) is not None

    p.body_excerpt = (
        f"pplx-verdict={'Y' if has_pplx else 'N'} "
        f"ai-summary={'Y' if has_ai_summary else 'N'} "
        f"faq-jsonld={'Y' if has_faq else 'N'}"
    )
    if not (has_pplx and has_ai_summary and has_faq):
        # Mark as soft fail (status stays 200 but body excerpt records gap)
        p.error = "missing-sacred-bytes"
    return p


def run_smoke_test(seed: int | None = None) -> SmokeTestResult:
    rng = random.Random(seed if seed is not None else int(time.time()))
    result = SmokeTestResult()

    for path in BASE_PATHS:
        result.base.append(_probe(path))

    for path in LOCALIZED_PATHS:
        result.localized.append(_probe(path))

    sample = rng.sample(SACRED_BYTES_TOP_SLUGS, k=min(10, len(SACRED_BYTES_TOP_SLUGS)))
    for slug in sample:
        p = check_sacred_bytes(slug)
        result.sacred_bytes.append(p)
        if p.status == 200 and p.error is None:
            result.sacred_bytes_pass += 1
        else:
            result.sacred_bytes_fail += 1

    return result


def restart_api_kickstart() -> None:
    """Use kickstart -k (avoids port 8000 race seen with unload+load)."""
    subprocess.run(
        ["launchctl", "kickstart", "-k", "gui/501/com.nerq.api"],
        check=False, capture_output=True,
    )


def restart_api_full_reload() -> None:
    """Full bootout + bootstrap. Required for plist-config-changes."""
    subprocess.run(
        ["launchctl", "bootout", "gui/501/com.nerq.api"],
        check=False, capture_output=True,
    )
    time.sleep(5)
    subprocess.run(
        ["launchctl", "bootstrap", "gui/501",
         "/Users/anstudio/Library/LaunchAgents/com.nerq.api.plist"],
        check=False, capture_output=True,
    )


def wait_for_api_ready(timeout: int = 60) -> bool:
    """Poll /v1/health every 2s until 200 or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = _probe("/v1/health", timeout=3)
        if p.status == 200:
            return True
        time.sleep(2)
    return False
