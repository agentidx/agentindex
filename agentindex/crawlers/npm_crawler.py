#!/usr/bin/env python3
"""
npm Registry Crawler v2
========================
Uses multiple search queries for broad coverage.
npm search API returns max ~5K per query, so we use 200+ diverse queries.

Also uses the registry directly for popular packages:
https://registry.npmjs.org/-/v1/search?text={query}&popularity=1.0&size=250
"""

import json, logging, sys, time, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import requests as http
from agentindex.db.models import get_session
from agentindex.crawlers.trust_calculator import calculate_trust
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
logger = logging.getLogger("npm_crawler")

# Diverse search terms to cover broad npm landscape
QUERIES = [
    # Top-level categories
    "react", "vue", "angular", "svelte", "next", "nuxt", "express", "fastify", "koa", "hapi",
    "typescript", "webpack", "vite", "rollup", "esbuild", "babel", "eslint", "prettier",
    "jest", "mocha", "vitest", "playwright", "cypress", "puppeteer",
    "axios", "fetch", "http", "request", "got", "node-fetch",
    "lodash", "ramda", "underscore", "moment", "dayjs", "date-fns",
    "mongodb", "mongoose", "prisma", "sequelize", "knex", "typeorm", "drizzle",
    "redis", "ioredis", "bull", "bullmq", "amqplib",
    "aws", "azure", "gcloud", "firebase", "supabase",
    "stripe", "paypal", "twilio", "sendgrid",
    "socket.io", "ws", "graphql", "apollo", "trpc",
    "tailwind", "bootstrap", "material", "chakra", "ant-design", "shadcn",
    "docker", "kubernetes", "terraform", "pulumi",
    "openai", "anthropic", "langchain", "ai", "llm", "mcp", "agent",
    "crypto", "blockchain", "ethereum", "solana", "web3",
    "cli", "commander", "yargs", "chalk", "ora", "inquirer",
    "sharp", "jimp", "canvas", "pdf", "excel", "csv",
    "email", "nodemailer", "smtp", "imap",
    "auth", "jwt", "passport", "oauth", "bcrypt",
    "logger", "winston", "pino", "bunyan", "morgan",
    "test", "mock", "stub", "faker", "chance",
    "stream", "pipe", "buffer", "zlib", "tar",
    "yaml", "toml", "ini", "dotenv", "config",
    "uuid", "nanoid", "cuid", "shortid",
    "validation", "joi", "zod", "yup", "ajv",
    "orm", "sql", "postgres", "mysql", "sqlite",
    "cache", "memcached", "lru", "ttl",
    "queue", "worker", "cron", "scheduler",
    "scraper", "cheerio", "jsdom", "selenium",
    "server", "middleware", "router", "proxy",
    "security", "helmet", "cors", "csrf", "xss",
    "upload", "multer", "formidable", "busboy",
    "image", "video", "audio", "ffmpeg",
    "map", "chart", "d3", "three", "canvas",
    "animation", "motion", "gsap", "lottie",
    "i18n", "intl", "locale", "translation",
    "notification", "push", "toast", "alert",
    "form", "input", "select", "date-picker",
    "table", "grid", "list", "virtual",
    "editor", "markdown", "rich-text", "code",
    "ai-sdk", "vercel", "netlify", "cloudflare",
    "monitoring", "sentry", "datadog", "newrelic",
]

STATE_FILE = Path(__file__).parent.parent.parent / "data" / "npm_crawl_state.json"


def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"query_index": 0, "seen_slugs": []}


def _save_state(state):
    # Keep state file manageable
    state["seen_slugs"] = state["seen_slugs"][-100000:]
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def crawl(limit=10000, query=None):
    logger.info(f"npm v2 crawl (limit={limit})")
    session = get_session()
    total = 0
    new = 0
    state = _load_state()
    seen = set(state.get("seen_slugs", []))
    qi = state.get("query_index", 0)

    queries = [query] if query else QUERIES

    for i, q in enumerate(queries):
        if query is None and i < qi:
            continue  # Resume from last position
        if total >= limit:
            break

        offset = 0
        empty_count = 0
        while total < limit and empty_count < 3:
            try:
                resp = http.get("https://registry.npmjs.org/-/v1/search",
                               params={"text": q, "size": 250, "from": offset,
                                       "popularity": "1.0"},
                               timeout=15)
                if resp.status_code != 200:
                    break
                objects = resp.json().get("objects", [])
                if not objects:
                    empty_count += 1
                    break
            except Exception as e:
                logger.warning(f"Search '{q}' error: {e}")
                break

            batch_new = 0
            for obj in objects:
                pkg = obj.get("package", {})
                name = pkg.get("name", "")
                if not name:
                    continue
                slug = name.lower().replace("/", "-").replace("@", "").replace(" ", "-")
                slug = re.sub(r"[^a-z0-9-]", "", slug).strip("-")

                if slug in seen:
                    total += 1
                    continue

                seen.add(slug)
                entry = {
                    "name": name, "slug": slug, "registry": "npm",
                    "version": pkg.get("version"),
                    "description": (pkg.get("description") or "")[:500],
                    "author": (pkg.get("publisher", {}) or {}).get("username", ""),
                    "license": None, "downloads": 0, "stars": 0,
                    "last_updated": pkg.get("date"),
                    "repository_url": (pkg.get("links", {}) or {}).get("repository"),
                    "homepage_url": (pkg.get("links", {}) or {}).get("homepage"),
                    "dependencies_count": 0,
                    "raw_data": json.dumps({"keywords": pkg.get("keywords", [])[:10],
                                           "score": obj.get("score", {}).get("final", 0)}),
                }
                entry["trust_score"], entry["trust_grade"] = calculate_trust(entry)
                try:
                    session.execute(text("""INSERT INTO software_registry
                        (name,slug,registry,version,description,author,license,downloads,stars,
                         last_updated,repository_url,homepage_url,dependencies_count,trust_score,trust_grade,raw_data)
                        VALUES (:name,:slug,:registry,:version,:description,:author,:license,:downloads,:stars,
                         :last_updated,:repository_url,:homepage_url,:dependencies_count,:trust_score,:trust_grade,CAST(:raw_data AS jsonb))
                        ON CONFLICT (registry,slug) DO UPDATE SET trust_score=EXCLUDED.trust_score,updated_at=NOW()
                    """), entry)
                    batch_new += 1
                    new += 1
                except Exception as e:
                    session.rollback()
                total += 1

            if batch_new == 0:
                empty_count += 1

            if total % 500 == 0:
                session.commit()
                logger.info(f"  {total} processed, {new} new (query: {q})")

            offset += len(objects)
            time.sleep(0.5)

        state["query_index"] = i + 1

    session.commit()
    session.close()

    state["seen_slugs"] = list(seen)
    _save_state(state)

    logger.info(f"npm v2 complete: {total} processed, {new} NEW packages added")
    return new


if __name__ == "__main__":
    crawl(int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
