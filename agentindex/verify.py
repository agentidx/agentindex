"""
AgentIndex Installation Verification

Run after installation to verify every component works.
Usage: python -m agentindex.verify

Checks:
1. Python dependencies
2. PostgreSQL connection
3. Redis connection
4. Ollama + model availability
5. Database schema
6. Each spider can initialize
7. Parser can initialize
8. API starts
9. End-to-end: insert test agent, query it, delete it
"""

import sys
import os
import time

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
CROSS = f"{RED}✗{RESET}"
WARN = f"{YELLOW}⚠{RESET}"

errors = []
warnings = []


def check(name: str, func):
    """Run a check and print result."""
    try:
        result = func()
        if result is True:
            print(f"  {CHECK} {name}")
        elif isinstance(result, str):
            print(f"  {WARN} {name}: {result}")
            warnings.append(f"{name}: {result}")
        else:
            print(f"  {CHECK} {name}: {result}")
    except Exception as e:
        print(f"  {CROSS} {name}: {e}")
        errors.append(f"{name}: {e}")


def main():
    print("\n" + "=" * 50)
    print("AgentIndex Installation Verification")
    print("=" * 50)

    from dotenv import load_dotenv
    load_dotenv()

    # 1. Dependencies
    print("\n1. Python Dependencies")

    def check_fastapi():
        import fastapi
        return f"v{fastapi.__version__}"
    check("FastAPI", check_fastapi)

    def check_sqlalchemy():
        import sqlalchemy
        return f"v{sqlalchemy.__version__}"
    check("SQLAlchemy", check_sqlalchemy)

    def check_httpx():
        import httpx
        return f"v{httpx.__version__}"
    check("httpx", check_httpx)

    def check_ollama():
        import ollama
        return True
    check("ollama", check_ollama)

    def check_pydantic():
        import pydantic
        return f"v{pydantic.__version__}"
    check("pydantic", check_pydantic)

    def check_apscheduler():
        import apscheduler
        return True
    check("APScheduler", check_apscheduler)

    def check_redis_lib():
        import redis
        return True
    check("redis", check_redis_lib)

    def check_github():
        from github import Github
        return True
    check("PyGithub", check_github)

    # 2. PostgreSQL
    print("\n2. PostgreSQL")

    def check_postgres():
        from sqlalchemy import create_engine, text
        url = os.getenv("DATABASE_URL", "postgresql://localhost/agentindex")
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            assert result == 1
        return url.split("/")[-1]
    check("Connection", check_postgres)

    def check_schema():
        from agentindex.db.models import init_db, get_session, Agent
        from sqlalchemy import select, func
        init_db()
        session = get_session()
        count = session.execute(select(func.count(Agent.id))).scalar()
        session.close()
        return f"OK ({count} agents in database)"
    check("Schema", check_schema)

    # 3. Redis
    print("\n3. Redis")

    def check_redis():
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(url)
        assert r.ping()
        return True
    check("Connection", check_redis)

    # 4. Ollama
    print("\n4. Ollama & Models")

    def check_ollama_server():
        from ollama import Client
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        client = Client(host=url)
        models = client.list()
        names = [m.get("name", "") for m in models.get("models", [])]
        return f"{len(names)} models: {', '.join(names[:5])}"
    check("Ollama server", check_ollama_server)

    def check_7b_model():
        from ollama import Client
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL_SMALL", "qwen2.5:7b")
        client = Client(host=url)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": "Respond with exactly: OK"}],
            options={"temperature": 0},
        )
        text = response["message"]["content"].strip()
        if "OK" in text:
            return f"{model} responding"
        return f"{model} responded but unexpected: {text[:50]}"
    check("7B model", check_7b_model)

    def check_72b_model():
        from ollama import Client
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL_LARGE", "qwen2.5:7b")
        client = Client(host=url)
        models = client.list()
        names = [m.get("name", "") for m in models.get("models", [])]
        if any(model in n for n in names):
            return f"{model} available"
        if model == os.getenv("OLLAMA_MODEL_SMALL", "qwen2.5:7b"):
            return f"Large model same as small ({model}) — OK for 16GB machine"
        return f"{model} not found — classifier will use fallback"
    check("Large model", check_72b_model)

    # 5. GitHub Token
    print("\n5. GitHub API")

    def check_github_token():
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return "GITHUB_TOKEN not set — GitHub spider will fail"
        from github import Github
        g = Github(token)
        rate = g.get_rate_limit()
        return f"Token valid, {rate.core.remaining}/{rate.core.limit} requests remaining"
    check("Token & rate limit", check_github_token)

    # 6. Spiders
    print("\n6. Spiders (initialization)")

    def check_github_spider():
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return "Skipped (no token)"
        from agentindex.spiders.github_spider import GitHubSpider
        spider = GitHubSpider()
        return True
    check("GitHub spider", check_github_spider)

    def check_npm_spider():
        from agentindex.spiders.npm_spider import NpmSpider
        spider = NpmSpider()
        return True
    check("npm spider", check_npm_spider)

    def check_pypi_spider():
        from agentindex.spiders.pypi_spider import PypiSpider
        spider = PypiSpider()
        return True
    check("PyPI spider", check_pypi_spider)

    def check_hf_spider():
        from agentindex.spiders.huggingface_spider import HuggingFaceSpider
        spider = HuggingFaceSpider()
        return True
    check("HuggingFace spider", check_hf_spider)

    def check_mcp_spider():
        from agentindex.spiders.mcp_spider import McpSpider
        spider = McpSpider()
        return True
    check("MCP spider", check_mcp_spider)

    # 7. Agents
    print("\n7. Agents (initialization)")

    def check_parser():
        from agentindex.agents.parser import Parser
        parser = Parser()
        return True
    check("Parser", check_parser)

    def check_classifier():
        from agentindex.agents.classifier import Classifier
        classifier = Classifier()
        return f"Using model: {classifier.model}"
    check("Classifier", check_classifier)

    def check_ranker():
        from agentindex.agents.ranker import Ranker
        ranker = Ranker()
        return True
    check("Ranker", check_ranker)

    def check_missionary():
        from agentindex.agents.missionary import Missionary
        m = Missionary()
        return True
    check("Missionary", check_missionary)

    # 8. API
    print("\n8. Discovery API")

    def check_api():
        from agentindex.api.discovery import app
        # Verify routes exist
        routes = [r.path for r in app.routes]
        expected = ["/v1/health", "/v1/discover", "/v1/stats"]
        for e in expected:
            assert e in routes, f"Missing route: {e}"
        return f"{len(routes)} routes registered"
    check("Routes", check_api)

    # 9. End-to-end test
    print("\n9. End-to-End Test")

    def check_e2e():
        from agentindex.db.models import Agent, get_session
        from sqlalchemy import select
        import uuid

        session = get_session()

        # Insert test agent
        test_id = uuid.uuid4()
        test_agent = Agent(
            id=test_id,
            source="test",
            source_url=f"https://test.example.com/{test_id}",
            source_id="test-agent",
            name="test-verify-agent",
            description="Temporary agent for verification",
            capabilities=["testing", "verification"],
            category="other",
            quality_score=0.5,
            crawl_status="ranked",
            is_active=True,
        )
        session.add(test_agent)
        session.commit()

        # Verify it exists
        found = session.execute(
            select(Agent).where(Agent.id == test_id)
        ).scalar_one_or_none()
        assert found is not None, "Test agent not found after insert"
        assert found.name == "test-verify-agent"

        # Clean up
        session.delete(found)
        session.commit()
        session.close()

        return "Insert → Query → Delete OK"
    check("Database round-trip", check_e2e)

    # Summary
    print("\n" + "=" * 50)
    if not errors and not warnings:
        print(f"{GREEN}ALL CHECKS PASSED{RESET}")
        print("System is ready. Start with: python -m agentindex.run")
    elif errors:
        print(f"{RED}ERRORS FOUND ({len(errors)}):{RESET}")
        for e in errors:
            print(f"  {CROSS} {e}")
        if warnings:
            print(f"\n{YELLOW}WARNINGS ({len(warnings)}):{RESET}")
            for w in warnings:
                print(f"  {WARN} {w}")
        print(f"\nFix errors before starting the system.")
    else:
        print(f"{GREEN}ALL CHECKS PASSED{RESET} with {len(warnings)} warnings:")
        for w in warnings:
            print(f"  {WARN} {w}")
        print("\nSystem is ready. Start with: python -m agentindex.run")
    print("=" * 50 + "\n")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
