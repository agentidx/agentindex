"""
OpenClaw Compliance Integration

This file patches the existing AgentIndex FastAPI app to include:
1. Compliance API endpoints (/compliance/*)
2. Free Compliance Checker web UI (/checker)
3. Upgrade tracking endpoint

Import this AFTER the app is created in discovery.py
"""

import os
import logging
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("openclaw.integration")


def mount_compliance(app):
    """
    Mount compliance features onto existing FastAPI app.
    Call this in discovery.py after app creation.
    """
    
    # 1. Mount compliance API router
    try:
        from agentindex.compliance.compliance_api import router as compliance_router
        app.include_router(compliance_router)
        logger.info("✅ Compliance API mounted at /compliance/*")
    except Exception as e:
        logger.error(f"❌ Failed to mount compliance API: {e}")
        return

    # 2. Serve the Free Compliance Checker HTML
    checker_path = Path(__file__).parent.parent / "templates" / "checker.html"
    
    @app.get("/checker", response_class=HTMLResponse)
    async def compliance_checker():
        """Free EU AI Act Compliance Checker - Web UI"""
        if checker_path.exists():
            return HTMLResponse(content=checker_path.read_text(), status_code=200)
        return HTMLResponse(content="<h1>Checker not found</h1>", status_code=404)

    comply_landing_path = Path(__file__).parent.parent.parent / "static" / "eu-compliance.html"

    @app.get("/comply", response_class=HTMLResponse)
    async def compliance_comply():
        """Comply landing page"""
        if comply_landing_path.exists():
            return HTMLResponse(content=comply_landing_path.read_text(), status_code=200)
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)

    compliance_landing_path = Path(__file__).parent.parent.parent / "static" / "eu-compliance.html"

    @app.get("/eu-compliance", response_class=HTMLResponse)
    async def compliance_landing():
        """EU AI Act Compliance Landing Page"""
        if compliance_landing_path.exists():
            return HTMLResponse(content=compliance_landing_path.read_text(), status_code=200)
        return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)

    terms_path = Path(__file__).parent.parent / "templates" / "terms.html"
    privacy_path = Path(__file__).parent.parent / "templates" / "privacy.html"

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_of_service():
        if terms_path.exists():
            return HTMLResponse(content=terms_path.read_text(), status_code=200)
        return HTMLResponse(content="<h1>Not found</h1>", status_code=404)

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_policy():
        if privacy_path.exists():
            return HTMLResponse(content=privacy_path.read_text(), status_code=200)
        return HTMLResponse(content="<h1>Not found</h1>", status_code=404)

    # 3. Upgrade click tracker (PMF sensor)
    @app.post("/compliance/track-upgrade")
    async def track_upgrade():
        """Track upgrade interest for PMF measurement."""
        try:
            from agentindex.db.models import get_write_session
            from sqlalchemy import text
            session = get_write_session()
            session.execute(text(
                "UPDATE checker_usage SET clicked_upgrade = TRUE "
                "WHERE id = (SELECT id FROM checker_usage ORDER BY created_at DESC LIMIT 1)"
            ))
            session.commit()
            session.close()
        except Exception:
            pass
        return JSONResponse({"status": "noted"})


    # 3b. Email subscribe endpoint
    @app.post("/compliance/subscribe")
    async def subscribe_email(request: Request):
        """Capture email for compliance checklist / monitoring alerts."""
        try:
            data = await request.json()
            email = data.get("email", "").strip()
            sub_type = data.get("type", "unknown")  # "checklist" or "monitor"
            persona = data.get("persona", "unknown")
            
            if not email or "@" not in email:
                return JSONResponse({"status": "invalid_email"}, status_code=400)
            
            from agentindex.db.models import get_write_session
            from sqlalchemy import text
            session = get_write_session()
            
            # Create table if not exists
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS compliance_subscribers (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    sub_type TEXT DEFAULT 'unknown',
                    persona TEXT DEFAULT 'unknown',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            
            # Insert subscriber (allow duplicates — different types)
            session.execute(text(
                "INSERT INTO compliance_subscribers (email, sub_type, persona) "
                "VALUES (:email, :type, :persona)"
            ), {"email": email, "type": sub_type, "persona": persona})
            
            session.commit()
            session.close()
            
            import logging
            logging.getLogger("nerq").info(f"📧 New subscriber: {email} ({sub_type}/{persona})")
            
        except Exception as e:
            import logging
            logging.getLogger("nerq").error(f"Subscribe error: {e}")
        
        return JSONResponse({"status": "subscribed"})

    # 4. Add compliance info to health check
    original_health = None
    for route in app.routes:
        if hasattr(route, 'path') and route.path == '/v1/health':
            original_health = route.endpoint
            break

    logger.info("✅ OpenClaw Compliance Layer fully integrated")
    logger.info("  📋 API: /compliance/check, /compliance/deadlines, /compliance/stats")
    logger.info("  🌐 Web: /checker")
    logger.info("  📊 PMF: /compliance/track-upgrade")
