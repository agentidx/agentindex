from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="agentindex-langchain",
    version="1.0.0",
    author="AgentIndex",
    author_email="support@agentcrawl.dev",
    description="AgentIndex integration for LangChain - discover 40,000+ agents with semantic search",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/agentidx/langchain-integration",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "langchain>=0.1.0",
        "requests>=2.25.0",
        "pydantic>=1.8.0"
    ],
    keywords="langchain agents ai discovery semantic-search agentindex",
    project_urls={
        "Homepage": "https://agentcrawl.dev",
        "Documentation": "https://api.agentcrawl.dev/docs",
        "Source": "https://github.com/agentidx/langchain-integration",
        "Tracker": "https://github.com/agentidx/langchain-integration/issues",
    }
)
