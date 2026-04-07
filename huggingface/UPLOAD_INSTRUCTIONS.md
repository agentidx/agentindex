# HuggingFace Dataset Upload Instructions

## Dataset: nerq/ai-agent-trust-scores

### Files ready for upload:
- `agents_trust_scores.csv` (1.4 MB, 10K agents)
- `agents_trust_scores.json` (4.5 MB, 10K agents)
- `README.md` (dataset card, CC-BY-4.0)

### Upload via CLI:
```bash
# Login first
huggingface-cli login

# Create and upload
huggingface-cli repo create ai-agent-trust-scores --type dataset --organization nerq
cd /Users/anstudio/agentindex/huggingface
huggingface-cli upload nerq/ai-agent-trust-scores . --repo-type dataset
```

### Upload via Python:
```python
from huggingface_hub import HfApi
api = HfApi()
api.create_repo("nerq/ai-agent-trust-scores", repo_type="dataset", exist_ok=True)
api.upload_folder(
    folder_path="/Users/anstudio/agentindex/huggingface",
    repo_id="nerq/ai-agent-trust-scores",
    repo_type="dataset"
)
```

### To refresh data:
```bash
PYTHONPATH=/Users/anstudio/agentindex python /Users/anstudio/agentindex/huggingface/create_dataset.py
```
