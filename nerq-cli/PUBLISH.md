# Publishing nerq CLI to PyPI

## Build
```bash
cd /Users/anstudio/agentindex/nerq-cli
pip install build twine
python -m build
```

## Publish
```bash
twine upload dist/nerq-1.1.0*
```

## Verify
```bash
pip install nerq==1.1.0
nerq check langchain
nerq scan requirements.txt
nerq recommend "code review"
nerq compare cursor continue-dev
```

## Changes in 1.1.0
- Added `nerq recommend <task>` command
- Added `nerq compare <a> <b>` command
- Improved terminal output formatting
- Added pre-commit hook support
