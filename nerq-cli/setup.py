from setuptools import setup

setup(
    name="nerq",
    version="1.1.0",
    py_modules=["nerq_cli"],
    entry_points={
        "console_scripts": [
            "nerq=nerq_cli:main",
            "nerq-pre-commit=nerq_cli:main",
        ],
    },
    python_requires=">=3.8",
    author="Anders Nilsson",
    author_email="anders@nerq.ai",
    description="AI agent trust verification CLI",
    url="https://nerq.ai",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
