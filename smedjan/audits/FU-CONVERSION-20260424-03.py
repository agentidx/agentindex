"""FU-CONVERSION-20260424-03 — QA render of 10 AI-landed /safe pages via headless Chrome.

Parent: AUDIT-CONVERSION-20260424, Finding 3. All 30 AI-referred sessions
over the last 30d bounced at 100% PV=1. Hypothesis: either the CTAs are
invisible above the fold or the page takes so long to render that the
reader leaves before anything becomes interactive.

This task takes the 10 /safe/* paths that AI sources (ChatGPT,
Perplexity, Claude, Kagi) actually landed on in the last 30d — evidence
at ~/smedjan/audit-reports/work-2026-04-24/q5_ai_landing_pages.json —
renders each in a real Chromium via the DevTools Protocol, and measures:

    - TTFB          (navigation timing, responseStart - requestStart)
    - LCP           (largest-contentful-paint entry, buffered)
    - load_ms       (loadEventEnd - navigationStart)
    - above_fold_ctas (count of visible interactive elements whose
                       bounding rect is within the 1280x800 viewport)
    - http_status
    - screenshot.png (1280x800 above-the-fold capture)

Output directory: ~/smedjan/audits/FU-CONVERSION-20260424-03/
    - <n>-<slug>.png    screenshots
    - results.json      raw metrics
    - FU-CONVERSION-20260424-03.md  markdown report

This script does NOT deploy anything and does NOT mutate the Nerq site.
It only performs read-only rendering of public pages.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Any

import websocket  # type: ignore[import-untyped]  # websocket-client 1.x

EVIDENCE_PATH = os.path.expanduser(
    "~/smedjan/audit-reports/work-2026-04-24/q5_ai_landing_pages.json"
)
OUT_DIR = os.path.expanduser("~/smedjan/audits/FU-CONVERSION-20260424-03")
REPORT_PATH = os.path.join(OUT_DIR, "FU-CONVERSION-20260424-03.md")
RESULTS_PATH = os.path.join(OUT_DIR, "results.json")

BASE_URL = "https://nerq.ai"
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VIEWPORT_W = 1280
VIEWPORT_H = 800
LCP_OBSERVE_MS = 4000        # wait this long after load for LCP entries
PER_PAGE_BUDGET_S = 25       # hard cap per page

TOP_N = 10


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.15)
    raise RuntimeError(f"Chrome did not open debug port {port} in {timeout}s")


def _load_paths() -> list[str]:
    with open(EVIDENCE_PATH) as f:
        rows = json.load(f)
    safe_paths: list[str] = []
    seen: set[str] = set()
    for row in rows:
        path = row[0]
        if not path.startswith("/safe/"):
            continue
        if path in seen:
            continue
        seen.add(path)
        safe_paths.append(path)
        if len(safe_paths) >= TOP_N:
            break
    return safe_paths


class CDPSession:
    """Minimal CDP client over a single target's websocket.

    Handles request/response correlation via `id` and buffers unmatched
    events for consumers that wait on specific event names.
    """

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self._next_id = 0
        self._events: list[dict[str, Any]] = []

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        self._next_id += 1
        msg_id = self._next_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Reset per-iteration; prior code paths may have mutated the
            # socket timeout, and we want the full remaining budget here.
            try:
                self.ws.settimeout(max(0.1, deadline - time.time()))
            except Exception:
                pass
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                continue
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error on {method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self._events.append(msg)
        raise RuntimeError(f"CDP timeout waiting for response to {method}")

    def wait_event(self, method: str, timeout: float = 20.0) -> dict[str, Any]:
        # First check buffered events
        for i, ev in enumerate(self._events):
            if ev.get("method") == method:
                self._events.pop(i)
                return ev.get("params", {})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.ws.settimeout(max(0.1, deadline - time.time()))
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            if not raw:
                continue
            msg = json.loads(raw)
            if msg.get("method") == method:
                return msg.get("params", {})
            if "method" in msg:
                self._events.append(msg)
        raise RuntimeError(f"CDP timeout waiting for event {method}")


def _measurement_js() -> str:
    return r"""
(async () => {
  // Collect LCP entries via a buffered PerformanceObserver so we pick up
  // entries that were emitted before the observer was attached.
  const lcpSeen = [];
  try {
    const po = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) lcpSeen.push(e);
    });
    po.observe({type: 'largest-contentful-paint', buffered: true});
  } catch (e) { /* older chrome / unsupported */ }

  // Give LCP observer a window to pick up late paints.
  await new Promise(r => setTimeout(r, __LCP_MS__));

  const nav = performance.getEntriesByType('navigation')[0] || {};
  const fallback = performance.getEntriesByType('largest-contentful-paint') || [];
  const combined = lcpSeen.length ? lcpSeen : fallback;
  let lcp = null;
  if (combined.length) {
    const last = combined[combined.length - 1];
    lcp = last.startTime || last.renderTime || last.loadTime || null;
  }

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const CTA_SEL = [
    'a[href]',
    'button',
    '[role="button"]',
    'input[type="submit"]',
    'input[type="button"]',
    '.btn', '.button', '.cta'
  ].join(',');

  const items = [];
  const seen = new Set();
  for (const el of document.querySelectorAll(CTA_SEL)) {
    if (seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.bottom <= 0) continue;            // above viewport
    if (r.top >= vh) continue;              // below the fold
    if (r.right <= 0 || r.left >= vw) continue; // outside horizontally
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (parseFloat(cs.opacity) < 0.1) continue;
    // Skip nested duplicates: if a child CTA is inside an ancestor that's
    // also matched, keep the innermost only.
    let ancestor = el.parentElement;
    let nestedDup = false;
    while (ancestor && ancestor !== document.body) {
      if (seen.has(ancestor) && items.some(it => it._el === ancestor)) {
        nestedDup = true; break;
      }
      ancestor = ancestor.parentElement;
    }
    if (nestedDup) continue;
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    items.push({
      _el: el,
      tag: el.tagName.toLowerCase(),
      text: txt.slice(0, 80),
      href: (el.getAttribute('href') || '').slice(0, 120),
      classes: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 80),
      top: Math.round(r.top),
      left: Math.round(r.left),
      width: Math.round(r.width),
      height: Math.round(r.height),
      has_text: txt.length > 0,
      has_img: !!el.querySelector('img,svg')
    });
  }
  for (const it of items) delete it._el;

  return {
    lcp_ms: lcp,
    ttfb_ms: nav.responseStart ? (nav.responseStart - nav.requestStart) : null,
    load_ms: nav.loadEventEnd ? nav.loadEventEnd : null,
    dcl_ms: nav.domContentLoadedEventEnd ? nav.domContentLoadedEventEnd : null,
    transfer_size: nav.transferSize || null,
    decoded_body_size: nav.decodedBodySize || null,
    viewport_w: vw,
    viewport_h: vh,
    above_fold_ctas: items.length,
    cta_items: items,
    doc_title: document.title,
    body_text_len: (document.body ? document.body.innerText.length : 0)
  };
})();
""".replace("__LCP_MS__", str(LCP_OBSERVE_MS))


def _measure_one(
    debug_port: int, url: str, screenshot_path: str
) -> dict[str, Any]:
    # Create a fresh target (tab) for this URL — about:blank then navigate.
    new_req = urllib.request.Request(
        f"http://127.0.0.1:{debug_port}/json/new?about:blank",
        method="PUT",
    )
    try:
        with urllib.request.urlopen(new_req, timeout=10) as resp:
            target = json.loads(resp.read())
    except urllib.error.HTTPError:
        # Older Chromes require GET for /json/new
        with urllib.request.urlopen(
            f"http://127.0.0.1:{debug_port}/json/new?about:blank", timeout=10
        ) as resp:
            target = json.loads(resp.read())

    target_id = target["id"]
    ws_url = target["webSocketDebuggerUrl"]
    session = CDPSession(ws_url)
    t0 = time.time()
    result: dict[str, Any] = {
        "url": url,
        "status": None,
        "error": None,
        "screenshot_path": None,
    }
    try:
        session.send("Page.enable")
        session.send("Network.enable")
        session.send("Runtime.enable")
        session.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": VIEWPORT_W,
                "height": VIEWPORT_H,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        session.send("Page.navigate", {"url": url})

        # Track the main frame response for http status.
        http_status = None
        got_load = False
        deadline = t0 + PER_PAGE_BUDGET_S - LCP_OBSERVE_MS / 1000 - 2

        def _handle(msg: dict[str, Any]) -> bool:
            nonlocal http_status, got_load
            meth = msg.get("method")
            if meth == "Network.responseReceived":
                p = msg.get("params", {})
                if p.get("type") == "Document" and http_status is None:
                    http_status = p.get("response", {}).get("status")
            elif meth == "Page.loadEventFired":
                got_load = True
                return True
            return False

        # Drain events buffered during the navigate round-trip first.
        pending = session._events
        session._events = []
        for buffered in pending:
            if _handle(buffered):
                break

        while not got_load and time.time() < deadline:
            try:
                session.ws.settimeout(max(0.1, deadline - time.time()))
                raw = session.ws.recv()
            except websocket.WebSocketTimeoutException:
                break
            if not raw:
                continue
            msg = json.loads(raw)
            if "method" in msg:
                _handle(msg)
        result["status"] = http_status

        if not got_load:
            result["error"] = "page did not fire load event within budget"
        else:
            js = _measurement_js()
            ev = session.send(
                "Runtime.evaluate",
                {
                    "expression": js,
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                timeout=LCP_OBSERVE_MS / 1000 + 15,
            )
            if ev.get("exceptionDetails"):
                result["error"] = f"runtime exception: {ev['exceptionDetails']}"
            else:
                metrics = ev.get("result", {}).get("value") or {}
                result.update(metrics)

            shot = session.send(
                "Page.captureScreenshot",
                {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
            )
            png_bytes = base64.b64decode(shot["data"])
            with open(screenshot_path, "wb") as f:
                f.write(png_bytes)
            result["screenshot_path"] = screenshot_path
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["wall_ms"] = int((time.time() - t0) * 1000)
        session.close()
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{debug_port}/json/close/{target_id}",
                timeout=5,
            ).read()
        except Exception:
            pass
    return result


def _launch_chrome(user_data_dir: str, port: int) -> subprocess.Popen[bytes]:
    args = [
        CHROME_BIN,
        "--headless=new",
        "--disable-gpu",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--disable-extensions",
        "--hide-scrollbars",
        "--mute-audio",
        f"--window-size={VIEWPORT_W},{VIEWPORT_H}",
        "about:blank",
    ]
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _slugify(path: str) -> str:
    s = path.strip("/").replace("/", "-")
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s)
    return s[:80] or "page"


def _fmt_ms(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.0f} ms"
    except Exception:
        return str(v)


def _lcp_verdict(lcp: Any) -> str:
    if lcp is None:
        return "no-lcp-observed"
    try:
        x = float(lcp)
    except Exception:
        return "unparseable"
    if x <= 2500:
        return "good"
    if x <= 4000:
        return "needs-improvement"
    return "poor"


def _render_report(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# FU-CONVERSION-20260424-03 — QA render of 10 AI-landed /safe pages")
    lines.append("")
    lines.append(
        "Parent: AUDIT-CONVERSION-20260424 · Finding 3 "
        "(30/30 AI-referred sessions bounced at PV=1 in last 30d)."
    )
    lines.append("")
    lines.append(
        f"Rendered each path in headless Chrome 147 at "
        f"{VIEWPORT_W}×{VIEWPORT_H}, measured Navigation Timing + LCP, "
        "counted above-the-fold interactive elements, captured a PNG of "
        "the first viewport."
    )
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append(
        "| # | Path | HTTP | TTFB | LCP | LCP verdict | Load | "
        "Above-fold CTAs | Screenshot |"
    )
    lines.append(
        "|---|------|------|------|-----|-------------|------|"
        "-----------------|------------|"
    )
    for i, r in enumerate(results, 1):
        short_path = r["url"].replace(BASE_URL, "")
        lines.append(
            "| {i} | `{p}` | {st} | {ttfb} | {lcp} | {verdict} | {load} | "
            "{ctas} | {shot} |".format(
                i=i,
                p=short_path,
                st=r.get("status") or "—",
                ttfb=_fmt_ms(r.get("ttfb_ms")),
                lcp=_fmt_ms(r.get("lcp_ms")),
                verdict=_lcp_verdict(r.get("lcp_ms")),
                load=_fmt_ms(r.get("load_ms")),
                ctas=(r.get("above_fold_ctas") if r.get("error") is None else "ERR"),
                shot=(os.path.basename(r["screenshot_path"])
                      if r.get("screenshot_path") else "—"),
            )
        )

    # Aggregates
    ok = [r for r in results if r.get("error") is None and r.get("status") == 200]
    lcps = [r["lcp_ms"] for r in ok if isinstance(r.get("lcp_ms"), (int, float))]
    ttfbs = [r["ttfb_ms"] for r in ok if isinstance(r.get("ttfb_ms"), (int, float))]
    ctas = [r["above_fold_ctas"] for r in ok
            if isinstance(r.get("above_fold_ctas"), (int, float))]

    def _mean(xs: list[float]) -> float | None:
        return (sum(xs) / len(xs)) if xs else None

    def _p95(xs: list[float]) -> float | None:
        if not xs:
            return None
        s = sorted(xs)
        idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
        return s[idx]

    lines.append("")
    lines.append("## Aggregates (200-OK pages only)")
    lines.append("")
    lines.append(f"- pages rendered ok: **{len(ok)} / {len(results)}**")
    lines.append(f"- TTFB mean: **{_fmt_ms(_mean(ttfbs))}**  p95: {_fmt_ms(_p95(ttfbs))}")
    lines.append(f"- LCP mean:  **{_fmt_ms(_mean(lcps))}**  p95: {_fmt_ms(_p95(lcps))}")
    if ctas:
        lines.append(
            f"- above-fold CTAs mean: **{_mean(ctas):.1f}**  "
            f"min: {int(min(ctas))}  max: {int(max(ctas))}"
        )
    lcp_poor = sum(1 for v in lcps if v and v > 4000)
    lcp_ni = sum(1 for v in lcps if v and 2500 < v <= 4000)
    lcp_good = sum(1 for v in lcps if v and v <= 2500)
    lines.append(
        f"- LCP verdict split: good={lcp_good}  needs-improvement={lcp_ni}  "
        f"poor={lcp_poor}  no-lcp={sum(1 for r in ok if not r.get('lcp_ms'))}"
    )

    lines.append("")
    lines.append("## Per-page detail")
    for i, r in enumerate(results, 1):
        short_path = r["url"].replace(BASE_URL, "")
        lines.append("")
        lines.append(f"### {i}. `{short_path}`")
        lines.append("")
        lines.append(f"- HTTP status: `{r.get('status')}`")
        lines.append(f"- TTFB: {_fmt_ms(r.get('ttfb_ms'))}")
        lines.append(
            f"- LCP:  {_fmt_ms(r.get('lcp_ms'))}  ({_lcp_verdict(r.get('lcp_ms'))})"
        )
        lines.append(f"- DOMContentLoaded: {_fmt_ms(r.get('dcl_ms'))}")
        lines.append(f"- loadEventEnd:     {_fmt_ms(r.get('load_ms'))}")
        lines.append(f"- transfer bytes:   {r.get('transfer_size') or '—'}")
        lines.append(f"- doc title:        `{(r.get('doc_title') or '').strip()[:140]}`")
        lines.append(f"- body text chars:  {r.get('body_text_len') or 0}")
        lines.append(f"- above-fold CTAs:  **{r.get('above_fold_ctas')}**")
        if r.get("error"):
            lines.append(f"- error: `{r['error']}`")
        items = r.get("cta_items") or []
        if items:
            lines.append("")
            lines.append(
                "  | tag | text | href | pos (top,left) | size |"
            )
            lines.append(
                "  |-----|------|------|----------------|------|"
            )
            for it in items[:30]:
                t = (it.get("text") or "").replace("|", "\\|") or "—"
                h = (it.get("href") or "").replace("|", "\\|") or "—"
                lines.append(
                    f"  | {it['tag']} | {t[:60]} | {h[:60]} | "
                    f"{it['top']},{it['left']} | {it['width']}×{it['height']} |"
                )
        if r.get("screenshot_path"):
            lines.append("")
            lines.append(
                f"![above-the-fold]({os.path.basename(r['screenshot_path'])})"
            )

    # Verdict block
    lines.append("")
    lines.append("## Verdict: does each page render a next-step?")
    lines.append("")
    lines.append(
        "A page is considered to render a next-step when at least one "
        "anchor/button with non-empty text is visible inside the first "
        f"{VIEWPORT_W}×{VIEWPORT_H} viewport."
    )
    lines.append("")
    lines.append("| Path | next-step above fold? | evidence |")
    lines.append("|------|-----------------------|----------|")
    for r in results:
        short_path = r["url"].replace(BASE_URL, "")
        items = r.get("cta_items") or []
        labelled = [
            it for it in items
            if (it.get("text") or "").strip() and it["tag"] in ("a", "button")
        ]
        has_next = len(labelled) > 0
        if r.get("error"):
            evidence = f"error: {r['error']}"
            has_next_label = "ERROR"
        else:
            evidence = (
                f"{len(items)} total interactive, {len(labelled)} with text"
                if items
                else "no interactive elements above the fold"
            )
            has_next_label = "yes" if has_next else "**no**"
        lines.append(f"| `{short_path}` | {has_next_label} | {evidence} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_Raw metrics in `results.json` alongside this report. "
        "Screenshots are the exact first viewport a human would see._"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    paths = _load_paths()
    if len(paths) < TOP_N:
        print(
            json.dumps({"error": f"only {len(paths)} /safe paths in evidence"}),
            file=sys.stderr,
        )
        # Still continue with what we have.
    print(f"[+] rendering {len(paths)} paths", file=sys.stderr)

    user_data_dir = tempfile.mkdtemp(prefix="fu-conversion-qa-")
    port = _pick_free_port()
    chrome = _launch_chrome(user_data_dir, port)
    try:
        _wait_for_port(port, timeout=10)
        # Give Chrome a beat to initialize the DevTools surface.
        time.sleep(0.5)

        results: list[dict[str, Any]] = []
        for i, path in enumerate(paths, 1):
            url = BASE_URL + path
            slug = _slugify(path)
            shot_path = os.path.join(OUT_DIR, f"{i:02d}-{slug}.png")
            print(f"[+] ({i}/{len(paths)}) {url}", file=sys.stderr)
            try:
                r = _measure_one(port, url, shot_path)
            except Exception as exc:
                r = {
                    "url": url,
                    "error": f"driver exception: {type(exc).__name__}: {exc}",
                    "status": None,
                    "screenshot_path": None,
                }
            results.append(r)

        report_md = _render_report(results)
        with open(REPORT_PATH, "w") as f:
            f.write(report_md)
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2, default=str)

        # Evidence summary for the orchestrator.
        ok = [r for r in results if r.get("error") is None and r.get("status") == 200]
        lcps = [r.get("lcp_ms") for r in ok if isinstance(r.get("lcp_ms"), (int, float))]
        ttfbs = [r.get("ttfb_ms") for r in ok if isinstance(r.get("ttfb_ms"), (int, float))]
        ctas = [r.get("above_fold_ctas") for r in ok
                if isinstance(r.get("above_fold_ctas"), (int, float))]
        no_cta_pages = [r["url"] for r in ok if (r.get("above_fold_ctas") or 0) == 0]

        evidence = {
            "report_path": REPORT_PATH,
            "results_path": RESULTS_PATH,
            "screenshot_dir": OUT_DIR,
            "pages_requested": len(paths),
            "pages_ok_200": len(ok),
            "ttfb_ms_mean": (sum(ttfbs) / len(ttfbs)) if ttfbs else None,
            "lcp_ms_mean": (sum(lcps) / len(lcps)) if lcps else None,
            "lcp_ms_p95": (sorted(lcps)[int(0.95 * (len(lcps) - 1))]
                           if lcps else None),
            "above_fold_ctas_mean": (sum(ctas) / len(ctas)) if ctas else None,
            "pages_with_zero_ctas_above_fold": no_cta_pages,
        }
        print(json.dumps(evidence, indent=2))
        return 0
    finally:
        try:
            chrome.send_signal(signal.SIGTERM)
            chrome.wait(timeout=5)
        except Exception:
            try:
                chrome.kill()
            except Exception:
                pass
        shutil.rmtree(user_data_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
