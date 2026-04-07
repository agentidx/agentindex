#!/usr/bin/env python3
"""
PyPI Crawler v2
================
1. Fetch https://pypi.org/simple/ → all package names (HTML, ~1MB)
2. For top N by alphabetical + seed list, fetch https://pypi.org/pypi/{name}/json
3. Rate limit: 2 req/sec
"""
import json, logging, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("pypi_crawler")

# High-priority packages (crawl these first)
SEED = [
    "boto3","requests","numpy","pandas","flask","django","fastapi","uvicorn",
    "openai","anthropic","langchain","langchain-core","transformers","torch",
    "tensorflow","huggingface-hub","datasets","accelerate","diffusers",
    "chromadb","pinecone-client","qdrant-client","weaviate-client",
    "crewai","autogen","llama-index","dspy-ai","semantic-kernel",
    "gradio","streamlit","wandb","mlflow","ray","vllm","litellm",
    "scikit-learn","xgboost","matplotlib","sqlalchemy","redis","celery",
    "pytest","black","ruff","docker","scrapy","selenium","playwright",
    "pydantic","httpx","aiohttp","pillow","scipy","click","rich",
    "typer","loguru","sentry-sdk","gunicorn","starlette","jinja2",
    "cryptography","psycopg2-binary","pymongo","alembic","pyyaml",
    "protobuf","grpcio","faiss-cpu","sentence-transformers","tokenizers",
    "safetensors","tiktoken","instructor","spacy","nltk","gensim",
    "peft","trl","deepspeed","bentoml","chainlit","langsmith","langfuse",
    "unstructured","docling","modal","fire","fabric","ansible-core",
    "orjson","msgpack","prometheus-client","structlog",
    "beautifulsoup4","lxml","html5lib","markdown","pygments",
    "tqdm","colorama","tabulate","arrow","pendulum",
    "pillow","opencv-python","imageio","scikit-image",
    "networkx","sympy","statsmodels","seaborn","plotly",
    "dask","polars","vaex","modin","pyarrow","parquet",
    "boto3","google-cloud-storage","azure-storage-blob",
    "stripe","twilio","sendgrid","slack-sdk",
    "celery","dramatiq","rq","huey","apscheduler",
    "sqlmodel","databases","encode-databases","piccolo",
    "starlite","litestar","sanic","aiohttp","quart","blacksheep",
    "pytest-asyncio","pytest-cov","coverage","nox","tox",
    "mypy","pyright","pylint","bandit","safety",
    "pre-commit","commitizen","semantic-release",
    "poetry","pipenv","hatch","flit","pdm","setuptools",
    "wheel","build","twine","cython","mypyc",
]

STATE_FILE = Path(__file__).parent.parent.parent / "data" / "pypi_crawl_state.json"


def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_offset": 0, "crawled": []}


def _save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def fetch_package_index():
    """Fetch all PyPI package names from the simple index."""
    logger.info("Fetching PyPI simple index...")
    try:
        r = http.get("https://pypi.org/simple/", timeout=60,
                     headers={"Accept": "application/vnd.pypi.simple.v1+json"})
        if r.status_code == 200:
            # JSON format
            data = r.json()
            names = [p.get("name", "") for p in data.get("projects", [])]
            logger.info(f"Got {len(names)} package names from JSON index")
            return names
    except Exception:
        pass

    # Fallback: HTML parsing
    try:
        r = http.get("https://pypi.org/simple/", timeout=60)
        if r.status_code == 200:
            names = re.findall(r'href="[^"]*/">([^<]+)</a>', r.text)
            logger.info(f"Got {len(names)} package names from HTML index")
            return names
    except Exception as e:
        logger.error(f"Failed to fetch index: {e}")
    return []


def crawl(limit=1000):
    logger.info(f"PyPI crawl v2 (limit={limit})")
    session = get_session()
    total = 0
    state = _load_state()
    already_crawled = set(state.get("crawled", []))

    # Build crawl list: seed packages first, then from index
    crawl_list = []
    for name in SEED:
        if name.lower() not in already_crawled:
            crawl_list.append(name)

    if len(crawl_list) < limit:
        # Fetch full index for more packages
        all_names = fetch_package_index()
        if all_names:
            offset = state.get("last_offset", 0)
            for name in all_names[offset:]:
                if name.lower() not in already_crawled and name not in crawl_list:
                    crawl_list.append(name)
                    if len(crawl_list) >= limit:
                        break
            state["last_offset"] = offset + limit

    logger.info(f"Crawl list: {len(crawl_list)} packages (seed: {min(len(SEED), limit)}, index: {max(0, len(crawl_list) - len(SEED))})")

    for name in crawl_list[:limit]:
        try:
            r = http.get(f"https://pypi.org/pypi/{name}/json", timeout=10)
            if r.status_code != 200:
                continue
            info = r.json().get("info", {})
            slug = name.lower().replace("_", "-").replace(" ", "-")

            entry = {
                "name": name, "slug": slug, "registry": "pypi",
                "version": info.get("version"),
                "description": (info.get("summary") or "")[:500],
                "author": (info.get("author") or info.get("maintainer") or "")[:100],
                "license": (info.get("license") or "")[:100],
                "downloads": 0, "stars": 0, "last_updated": None,
                "repository_url": _find_repo_url(info),
                "homepage_url": info.get("home_page") or info.get("project_url"),
                "dependencies_count": len(info.get("requires_dist") or []),
                "raw_data": json.dumps({"requires_python": info.get("requires_python"),
                                       "keywords": (info.get("keywords") or "")[:200]}),
            }
            entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)

            session.execute(text("""INSERT INTO software_registry
                (name,slug,registry,version,description,author,license,downloads,stars,
                 last_updated,repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                 :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                ON CONFLICT (registry,slug) DO UPDATE SET
                 trust_score=EXCLUDED.trust_score,description=EXCLUDED.description,
                 version=EXCLUDED.version,author=EXCLUDED.author,updated_at=NOW()
            """), entry)
            total += 1
            already_crawled.add(name.lower())

            if total % 50 == 0:
                session.commit()
                logger.info(f"  {total} packages crawled...")

        except Exception as e:
            logger.warning(f"{name}: {e}")
            session.rollback()
        time.sleep(0.5)  # 2 req/sec

    session.commit()
    session.close()

    state["crawled"] = list(already_crawled)[:50000]  # Cap state size
    _save_state(state)

    logger.info(f"PyPI v2 complete: {total} packages crawled")
    return total


def _find_repo_url(info):
    """Extract repository URL from project_urls or home_page."""
    urls = info.get("project_urls") or {}
    for key in ["Source", "Repository", "Source Code", "GitHub", "Code", "Homepage"]:
        if key in urls and urls[key]:
            return urls[key]
    hp = info.get("home_page") or ""
    if "github.com" in hp or "gitlab.com" in hp:
        return hp
    return ""


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
