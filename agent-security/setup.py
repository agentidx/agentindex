from setuptools import setup, find_packages

setup(
    name="agent-security",
    version="1.0.0",
    description="Security scanner for AI agent dependencies. One command to know if your AI stack is safe.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nerq",
    author_email="hello@nerq.ai",
    url="https://nerq.ai",
    project_urls={
        "Homepage": "https://nerq.ai",
        "Documentation": "https://nerq.ai/start",
        "Repository": "https://github.com/agentic-index/agent-security",
    },
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "agent-security=agent_security.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Security",
        "Topic :: Software Development :: Quality Assurance",
    ],
    keywords=["ai", "agents", "security", "trust", "cve", "scanner", "mcp"],
    license="MIT",
)
