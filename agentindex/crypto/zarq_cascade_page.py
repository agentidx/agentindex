import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "zarq_cascade_risk.html")

def mount_cascade_page(app: FastAPI):
    @app.get("/cascade-risk", response_class=HTMLResponse, include_in_schema=False)
    def cascade_risk_page():
        if os.path.exists(TEMPLATE_PATH):
            with open(TEMPLATE_PATH) as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(status_code=404, content="<h1>Cascade Risk page not found</h1>")

    @app.get("/cascade", response_class=HTMLResponse, include_in_schema=False)
    def cascade_redirect():
        return RedirectResponse(url="/cascade-risk")
