from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="nerq",
    version="1.0.0",
    description="Nerq Trust API — Preflight trust checks for AI agents and MCP servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nerq",
    author_email="api@nerq.ai",
    url="https://nerq.ai",
    project_urls={
        "Documentation": "https://nerq.ai/nerq/docs",
        "API Reference": "https://nerq.ai/docs",
        "Source": "https://github.com/nerq-ai/nerq-python",
    },
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Security",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=[
        "ai-agents", "trust-score", "mcp", "preflight",
        "agent-safety", "trust-verification", "agentic-economy",
    ],
)
