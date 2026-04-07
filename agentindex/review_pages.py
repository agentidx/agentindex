"""
Nerq User Review Pages
=======================
Review page at /review/{name} and POST /v1/agent/review endpoint.
Lets users submit star ratings and comments for AI agents.

Usage in discovery.py:
    from agentindex.review_pages import mount_review_pages
    mount_review_pages(app)
"""

import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.review_pages")

# Rate limiting: IP hash -> list of timestamps
_rate_limit: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 3600  # 1 hour


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _esc_json(s):
    if not s:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _ensure_reviews_table():
    """Create user_reviews table if it doesn't exist."""
    session = get_session()
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS user_reviews (
                id SERIAL PRIMARY KEY,
                agent_name TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                comment TEXT,
                reviewer_name TEXT DEFAULT 'Anonymous',
                ip_hash TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                is_editorial BOOLEAN DEFAULT FALSE
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_reviews_agent ON user_reviews(agent_name)
        """))
        session.commit()
        logger.info("user_reviews table ensured")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to create user_reviews table: {e}")
    finally:
        session.close()


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(f"nerq-review-salt-{ip}".encode()).hexdigest()[:16]


def _check_rate_limit(ip_hash: str) -> bool:
    """Return True if request is within rate limit."""
    now = time.time()
    # Clean old entries
    _rate_limit[ip_hash] = [t for t in _rate_limit[ip_hash] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit[ip_hash]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit[ip_hash].append(now)
    return True


def _lookup_agent_for_review(name: str):
    """Look up agent by name for the review page."""
    session = get_session()
    try:
        clean = name.replace("-", " ").replace("_", " ")
        row = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                   trust_grade, category, source, stars, description
            FROM entity_lookup
            WHERE (name_lower = LOWER(:name) OR name_lower = LOWER(:clean)
                   OR name_lower LIKE lower(:pattern))
              AND is_active = true
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {"name": name, "clean": clean, "pattern": f"%{name}%"}).fetchone()
        return dict(row._mapping) if row else None
    finally:
        session.close()


def _get_reviews(agent_name: str, limit: int = 10):
    """Get reviews for an agent."""
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT rating, comment, reviewer_name, created_at, is_editorial
            FROM user_reviews
            WHERE agent_name = :name
            ORDER BY is_editorial DESC, created_at DESC
            LIMIT :lim
        """), {"name": agent_name, "lim": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def _get_review_stats(agent_name: str):
    """Get average rating and count for an agent."""
    session = get_session()
    try:
        row = session.execute(text("""
            SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
            FROM user_reviews
            WHERE agent_name = :name
        """), {"name": agent_name}).fetchone()
        if row:
            r = dict(row._mapping)
            return {
                "avg_rating": round(float(r["avg_rating"]), 1) if r["avg_rating"] else 0,
                "review_count": int(r["review_count"]) if r["review_count"] else 0,
            }
        return {"avg_rating": 0, "review_count": 0}
    finally:
        session.close()


def _render_stars_display(rating: float, size: str = "16px") -> str:
    """Render star display for a given rating."""
    full = int(rating)
    half = 1 if rating - full >= 0.5 else 0
    empty = 5 - full - half
    html = ""
    for _ in range(full):
        html += f'<span style="color:#f59e0b;font-size:{size}">&#9733;</span>'
    for _ in range(half):
        html += f'<span style="color:#f59e0b;font-size:{size}">&#9733;</span>'
    for _ in range(empty):
        html += f'<span style="color:#d1d5db;font-size:{size}">&#9733;</span>'
    return html


def _render_review_page(name: str):
    """Render the review submission page."""
    agent = _lookup_agent_for_review(name)
    if not agent:
        return None

    agent_name = agent.get("name") or name
    score = agent.get("trust_score") or 0
    score_str = f"{score:.1f}" if isinstance(score, float) else str(score)
    grade = agent.get("trust_grade") or "N/A"
    category = agent.get("category") or "uncategorized"

    # Get existing reviews
    stats = _get_review_stats(agent_name)
    reviews = _get_reviews(agent_name)

    reviews_html = ""
    if reviews:
        for rv in reviews:
            rating = rv.get("rating", 0)
            comment = rv.get("comment") or ""
            reviewer = rv.get("reviewer_name") or "Anonymous"
            created = rv.get("created_at") or ""
            is_editorial = rv.get("is_editorial", False)
            editorial_badge = ' <span style="background:#ecfdf5;color:#065f46;padding:1px 6px;font-size:11px;font-weight:600;border:1px solid #a7f3d0">Editorial</span>' if is_editorial else ""
            date_str = str(created)[:10] if created else ""
            reviews_html += f'''<div style="border:1px solid #1f1f1f;padding:16px;margin-bottom:12px;background:#111">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div>{_render_stars_display(rating, "14px")} <span style="color:#9ca3af;font-size:13px;margin-left:4px">{_esc(reviewer)}{editorial_badge}</span></div>
    <span style="color:#6b7280;font-size:12px">{_esc(date_str)}</span>
  </div>
  <p style="color:#d1d5db;font-size:14px;line-height:1.6;margin:0">{_esc(comment)}</p>
</div>'''

    avg_stars_html = _render_stars_display(stats["avg_rating"], "20px") if stats["review_count"] > 0 else '<span style="color:#6b7280">No reviews yet</span>'
    avg_text = f'{stats["avg_rating"]}/5 ({stats["review_count"]} review{"s" if stats["review_count"] != 1 else ""})' if stats["review_count"] > 0 else ""

    # JSON-LD
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Review {agent_name} — Nerq",
        "description": f"Submit a review for {agent_name}. Current trust score: {score_str}/100.",
        "url": f"https://nerq.ai/review/{name}",
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
    })
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Agent Safety", "item": "https://nerq.ai/safe"},
            {"@type": "ListItem", "position": 3, "name": agent_name, "item": f"https://nerq.ai/safe/{name}"},
            {"@type": "ListItem", "position": 4, "name": "Review"},
        ]
    })

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review {_esc(agent_name)} — Nerq Trust Score {score_str}/100</title>
<meta name="description" content="Submit a review for {_esc(agent_name)}. Current Nerq Trust Score: {score_str}/100 ({_esc(grade)}). Read community reviews and ratings.">
<link rel="canonical" href="https://nerq.ai/review/{_esc(name)}">
<meta property="og:title" content="Review {_esc(agent_name)} — Nerq">
<meta property="og:description" content="Rate and review {_esc(agent_name)}. Trust Score: {score_str}/100.">
<meta property="og:url" content="https://nerq.ai/review/{_esc(name)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<style>
{NERQ_CSS}
body{{background:#0a0a0a;color:#e5e7eb}}
a{{color:#00d4aa}}
a:hover{{color:#00b894}}
nav{{border-bottom:1px solid #1f1f1f}}
nav .links a{{color:#9ca3af}}
nav .links a:hover{{color:#00d4aa}}
footer{{border-top:1px solid #1f1f1f;color:#6b7280}}
h1,h2,h3{{color:#f9fafb}}
.breadcrumb a{{color:#6b7280}}
.breadcrumb a:hover{{color:#00d4aa}}
.score-box{{text-align:center;padding:24px;border:1px solid #1f1f1f;margin:16px 0;background:#111}}
.score-box .big-score{{font-family:ui-monospace,'SF Mono',monospace;font-size:3rem;font-weight:700;color:#00d4aa;line-height:1}}
.score-box .score-sub{{font-size:14px;color:#6b7280;margin-top:4px}}
.review-form{{border:1px solid #1f1f1f;padding:24px;margin:20px 0;background:#111}}
.star-rating{{display:flex;flex-direction:row-reverse;justify-content:flex-end;gap:4px;margin:8px 0 16px}}
.star-rating input{{display:none}}
.star-rating label{{font-size:28px;color:#374151;cursor:pointer;transition:color 0.15s}}
.star-rating label:hover,.star-rating label:hover~label{{color:#f59e0b}}
.star-rating input:checked~label{{color:#f59e0b}}
.form-group{{margin-bottom:16px}}
.form-group label{{display:block;font-size:13px;color:#9ca3af;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.03em}}
.form-group textarea{{width:100%;padding:10px 12px;background:#0a0a0a;border:1px solid #1f1f1f;color:#e5e7eb;font-family:system-ui,-apple-system,sans-serif;font-size:14px;resize:vertical;min-height:80px}}
.form-group textarea:focus{{border-color:#00d4aa;outline:none}}
.form-group input[type=text]{{width:100%;padding:10px 12px;background:#0a0a0a;border:1px solid #1f1f1f;color:#e5e7eb;font-family:system-ui,-apple-system,sans-serif;font-size:14px}}
.form-group input[type=text]:focus{{border-color:#00d4aa;outline:none}}
.submit-btn{{padding:10px 28px;background:#00d4aa;color:#0a0a0a;border:none;font-size:14px;font-weight:700;cursor:pointer;font-family:system-ui,-apple-system,sans-serif}}
.submit-btn:hover{{background:#00b894}}
.submit-btn:disabled{{opacity:0.5;cursor:not-allowed}}
.success-msg{{background:#064e3b;border:1px solid #065f46;padding:16px;margin:16px 0;color:#a7f3d0;font-size:14px;display:none}}
.error-msg{{background:#7f1d1d;border:1px solid #991b1b;padding:16px;margin:16px 0;color:#fecaca;font-size:14px;display:none}}
.reviews-section{{margin:24px 0}}
.avg-block{{display:flex;align-items:center;gap:12px;margin:8px 0 16px}}
</style>
</head>
<body>
{NERQ_NAV}

<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/safe">safety</a> &rsaquo; <a href="/safe/{_esc(name)}">{_esc(agent_name)}</a> &rsaquo; review</div>

  <h1>Review {_esc(agent_name)}</h1>
  <p style="color:#9ca3af;font-size:14px;margin:4px 0 0">{_esc(category)} &middot; Trust Score: {score_str}/100 &middot; Grade: {_esc(grade)}</p>

  <div class="score-box">
    <div class="big-score">{score_str}</div>
    <div class="score-sub">Nerq Trust Score out of 100</div>
  </div>

  <div class="reviews-section">
    <h2>Community Reviews</h2>
    <div class="avg-block">
      {avg_stars_html}
      <span style="color:#9ca3af;font-size:14px">{_esc(avg_text)}</span>
    </div>
    {reviews_html if reviews_html else '<p style="color:#6b7280;font-size:14px">No reviews yet. Be the first to review this agent.</p>'}
  </div>

  <div class="review-form" id="review-form">
    <h2 style="margin-top:0;border-top:none;padding-top:0">Submit Your Review</h2>

    <div id="success-msg" class="success-msg">Thank you! Your review has been submitted.</div>
    <div id="error-msg" class="error-msg"></div>

    <form id="reviewForm" onsubmit="return submitReview(event)">
      <div class="form-group">
        <label>Rating</label>
        <div class="star-rating">
          <input type="radio" id="star5" name="rating" value="5"><label for="star5">&#9733;</label>
          <input type="radio" id="star4" name="rating" value="4"><label for="star4">&#9733;</label>
          <input type="radio" id="star3" name="rating" value="3" checked><label for="star3">&#9733;</label>
          <input type="radio" id="star2" name="rating" value="2"><label for="star2">&#9733;</label>
          <input type="radio" id="star1" name="rating" value="1"><label for="star1">&#9733;</label>
        </div>
      </div>

      <div class="form-group">
        <label for="comment">Comment</label>
        <textarea id="comment" name="comment" placeholder="Share your experience with {_esc(agent_name)}..."></textarea>
      </div>

      <div class="form-group">
        <label for="reviewer_name">Your Name (optional)</label>
        <input type="text" id="reviewer_name" name="reviewer_name" placeholder="Anonymous" maxlength="100">
      </div>

      <button type="submit" class="submit-btn" id="submitBtn">Submit Review</button>
    </form>
  </div>

  <div style="display:flex;gap:12px;flex-wrap:wrap;margin:24px 0">
    <a href="/safe/{_esc(name)}" style="display:inline-block;padding:8px 20px;border:1px solid #00d4aa;color:#00d4aa;font-size:14px;font-weight:600;text-decoration:none">Safety Report</a>
    <a href="/kya/{_esc(agent_name)}" style="display:inline-block;padding:8px 20px;border:1px solid #1f1f1f;color:#9ca3af;font-size:14px;font-weight:600;text-decoration:none">Full KYA Report</a>
  </div>

  <p style="margin-top:24px;font-size:12px;color:#6b7280">
    <strong>Disclaimer:</strong> Reviews are user-submitted opinions. Nerq does not verify review authenticity. Trust scores are independently computed from public signals.
  </p>
</main>

{NERQ_FOOTER}

<script>
async function submitReview(e) {{
  e.preventDefault();
  var btn = document.getElementById('submitBtn');
  var successMsg = document.getElementById('success-msg');
  var errorMsg = document.getElementById('error-msg');
  btn.disabled = true;
  successMsg.style.display = 'none';
  errorMsg.style.display = 'none';

  var rating = document.querySelector('input[name="rating"]:checked');
  if (!rating) {{
    errorMsg.textContent = 'Please select a rating.';
    errorMsg.style.display = 'block';
    btn.disabled = false;
    return false;
  }}

  var comment = document.getElementById('comment').value.trim();
  var reviewer_name = document.getElementById('reviewer_name').value.trim() || 'Anonymous';

  try {{
    var resp = await fetch('/v1/agent/review', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        agent_name: '{_esc_json(agent_name)}',
        rating: parseInt(rating.value),
        comment: comment,
        reviewer_name: reviewer_name
      }})
    }});
    var data = await resp.json();
    if (resp.ok) {{
      successMsg.style.display = 'block';
      document.getElementById('reviewForm').style.display = 'none';
    }} else {{
      errorMsg.textContent = data.detail || 'Failed to submit review. Please try again.';
      errorMsg.style.display = 'block';
      btn.disabled = false;
    }}
  }} catch(err) {{
    errorMsg.textContent = 'Network error. Please try again.';
    errorMsg.style.display = 'block';
    btn.disabled = false;
  }}
  return false;
}}
</script>
</body>
</html>'''
    return html


def mount_review_pages(app):
    """Mount /review/{name} and POST /v1/agent/review."""
    _ensure_reviews_table()

    @app.get("/review/{name:path}", response_class=HTMLResponse)
    async def review_page(name: str):
        try:
            html = _render_review_page(name)
            if html is None:
                _dn = name.replace("-", " ").replace("/", " ").title()
                return HTMLResponse(status_code=200, content=f'<html><head><title>{_dn} Review | Nerq</title><meta name="robots" content="noindex"><link rel="stylesheet" href="/static/nerq.css?v=13"></head><body><h1>{_dn} — Not Yet Reviewed</h1><p>This tool has been queued for review. <a href="/">Search Nerq</a></p></body></html>')
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering review page for {name}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.post("/v1/agent/review")
    async def submit_review(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})

        agent_name = body.get("agent_name", "").strip()
        rating = body.get("rating")
        comment = body.get("comment", "").strip()
        reviewer_name = body.get("reviewer_name", "Anonymous").strip() or "Anonymous"

        if not agent_name:
            return JSONResponse(status_code=400, content={"detail": "agent_name is required"})
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return JSONResponse(status_code=400, content={"detail": "rating must be an integer between 1 and 5"})
        if len(comment) > 2000:
            return JSONResponse(status_code=400, content={"detail": "comment must be 2000 characters or less"})
        if len(reviewer_name) > 100:
            reviewer_name = reviewer_name[:100]

        # Rate limit by IP
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = _hash_ip(client_ip)
        if not _check_rate_limit(ip_hash):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Max 10 reviews per hour."})

        session = get_session()
        try:
            session.execute(text("""
                INSERT INTO user_reviews (agent_name, rating, comment, reviewer_name, ip_hash)
                VALUES (:agent_name, :rating, :comment, :reviewer_name, :ip_hash)
            """), {
                "agent_name": agent_name,
                "rating": rating,
                "comment": comment,
                "reviewer_name": reviewer_name,
                "ip_hash": ip_hash,
            })
            session.commit()
            logger.info(f"Review submitted for {agent_name}: {rating} stars by {reviewer_name}")
            return JSONResponse(status_code=201, content={"status": "created"})
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to insert review: {e}")
            return JSONResponse(status_code=500, content={"detail": "Failed to save review"})
        finally:
            session.close()

    logger.info("Mounted review pages: /review/{name}, POST /v1/agent/review")
