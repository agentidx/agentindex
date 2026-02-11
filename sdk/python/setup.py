from setuptools import setup, find_packages

setup(
    name="agentcrawl",
    version="0.3.0",
    description="Discovery service for AI agents. Find any agent by capability.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="AgentIndex",
    url="https://github.com/agentindex/agentindex-sdk-python",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["httpx>=0.25.0"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    keywords="ai agent discovery mcp a2a llm autonomous multi-agent",
)
