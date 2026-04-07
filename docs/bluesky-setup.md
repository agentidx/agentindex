# Bluesky Bot Setup

The Nerq Scout posts daily summaries to Bluesky after each run.

## 1. Create a Bluesky account

Go to [bsky.app](https://bsky.app) and create an account (e.g. `nerq.bsky.social`).

## 2. Create an app password

1. Log in to Bluesky
2. Go to **Settings** > **Privacy and security** > **App passwords**
3. Click **Add App Password**
4. Name it `nerq-bot` and save the generated password

## 3. Save credentials

```bash
mkdir -p ~/.config/nerq
echo "nerq.bsky.social" > ~/.config/nerq/bluesky_handle
echo "xxxx-xxxx-xxxx-xxxx" > ~/.config/nerq/bluesky_app_password
chmod 600 ~/.config/nerq/bluesky_app_password
```

Replace `nerq.bsky.social` with your actual handle and `xxxx-xxxx-xxxx-xxxx` with the app password.

## 4. Test

```bash
python3 -m agentindex.bluesky_bot
```

This runs a dry run that validates credentials, tests facet extraction, and shows a sample post without actually posting.

## 5. How it works

- After each Scout run (`python3 -m agentindex.nerq_scout_agent`), the bot posts a summary
- Format: `Nerq Scout: {top_agent} scored {score} ({grade}). {count} agents evaluated today. https://nerq.ai/blog`
- Links are clickable (AT Protocol facets)
- Max 300 chars per post
- If no credentials are found, posting is skipped gracefully

## Manual posting

```python
from agentindex.bluesky_bot import post_to_bluesky, post_benchmark_summary

# Post custom text
post_to_bluesky("Your text here https://nerq.ai")

# Post benchmark summary
post_benchmark_summary()
```
