# Publish zarq-langchain to PyPI

**Date:** 2026-03-08
**Status:** Ready to Upload (Anders)

---

## What Was Done

### 1. Fixed Package Structure
The original layout had `zarq_langchain.py` and `__init__.py` loose in the root — setuptools couldn't find the package (empty `top_level.txt`). Restructured to proper package directory:

```
integrations/langchain/
├── pyproject.toml
├── README.md
├── __init__.py          ← old (kept for backwards compat)
├── zarq_langchain.py    ← old (kept for backwards compat)
└── zarq_langchain/      ← NEW proper package dir
    ├── __init__.py
    └── zarq_langchain.py
```

### 2. Fixed Deprecation Warnings
- `license = {text = "MIT"}` → `license = "MIT"` (SPDX format)
- Removed deprecated `License :: OSI Approved :: MIT License` classifier

### 3. Updated README
- Removed "coming soon" from `pip install zarq-langchain`

### 4. Built Successfully
```
dist/zarq_langchain-0.1.0-py3-none-any.whl  (4.2KB)
dist/zarq_langchain-0.1.0.tar.gz            (3.8KB)
```

Wheel contents verified:
- `zarq_langchain/__init__.py`
- `zarq_langchain/zarq_langchain.py`
- METADATA, WHEEL, top_level.txt, RECORD

### 5. Twine Available
`twine 6.2.0` installed in venv — ready to upload.

## Regarding Existing 'zarq' Package

PyPI blocked the fetch (bot protection), so couldn't verify contents. The `zarq` package was published Mar 5. **Recommendation:** publish as `zarq-langchain` (separate package) for now. This is the standard convention (cf. `langchain-openai`, `langchain-anthropic`). Can always add `zarq-langchain` as an optional dependency of `zarq` later.

## Command for Anders

```bash
cd ~/agentindex/integrations/langchain
twine upload dist/*
```

You'll be prompted for PyPI credentials (or use `~/.pypirc` / `TWINE_USERNAME` + `TWINE_PASSWORD` env vars).

After upload, verify:
```bash
pip install zarq-langchain
python -c "from zarq_langchain import ZARQRiskCheck; print(ZARQRiskCheck().run('bitcoin'))"
```
