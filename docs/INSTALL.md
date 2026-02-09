# AgentIndex — Installationsguide
## Mac Mini M4 (16GB) — bredvid OpenClaw

Din maskin: Mac Mini M4, 10 kärnor, 16GB RAM, 1TB lagring
OpenClaw körs redan — vi installerar AgentIndex bredvid.

Uppskattad tid: ~45 minuter

---

### Steg 1: Kontrollera att Homebrew finns

Öppna Terminal:

```bash
brew --version
```

Om det inte finns, installera:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Steg 2: Installera det som saknas

Kolla först vad du redan har (OpenClaw kanske installerat en del):

```bash
which python3 && python3 --version
which psql
which redis-server
which ollama
```

Installera det som saknas:
```bash
brew install python@3.12 postgresql@16 redis nginx ollama
```

Om du redan har Tailscale (för fjärråtkomst) — bra. Annars:
```bash
brew install tailscale
```

### Steg 3: Starta databaser

```bash
brew services start postgresql@16
createdb agentindex
brew services start redis
```

Verifiera:
```bash
psql agentindex -c "SELECT 1;"
redis-cli ping
```

### Steg 4: Installera AI-modell via Ollama

```bash
# Om Ollama inte redan körs:
brew services start ollama
# Vänta 10 sekunder

ollama pull qwen2.5:7b
```

OBS: Vi installerar BARA 7B-modellen (~5GB RAM).
72B väntar tills din 64GB-maskin levereras.

Verifiera:
```bash
ollama run qwen2.5:7b "Respond with OK"
```

### Steg 5: Installera AgentIndex

```bash
cd ~
mkdir -p agentindex && cd agentindex

# Packa upp tar.gz-filen du laddade ner från Claude
tar xzf ~/Downloads/agentindex-v0.2.tar.gz

# Skapa virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Installera dependencies
pip install -r requirements.txt
```

### Steg 6: Konfigurera

```bash
cp .env.example .env
nano .env
```

Ändra:
```
GITHUB_TOKEN=ghp_ditt_token_här
OLLAMA_MODEL_SMALL=qwen2.5:7b
OLLAMA_MODEL_LARGE=qwen2.5:7b
API_PORT=8100
```

**Skaffa GitHub-token:**
github.com → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
Permissions: Public repositories (read-only)

### Steg 7: Initiera databas och testa

```bash
source venv/bin/activate
python -c "from agentindex.db.models import init_db; init_db()"
python -c "
from agentindex.spiders.github_spider import GitHubSpider
spider = GitHubSpider()
print('Rate limit:', spider.get_remaining_rate_limit())
"
```

### Steg 8: Starta systemet

```bash
cd ~/agentindex
source venv/bin/activate
python -m agentindex.run
```

Du bör se:
```
AgentIndex starting...
Database initialized successfully.
Discovery API started on port 8100
Starting GitHub crawl...
```

### Steg 9: Kör i bakgrunden

```bash
cd ~/agentindex && source venv/bin/activate
nohup python -m agentindex.run > agentindex.log 2>&1 &
echo $! > agentindex.pid
```

Kolla loggen: `tail -f ~/agentindex/agentindex.log`
Stoppa: `kill $(cat ~/agentindex/agentindex.pid)`

### Steg 10: Automatisk start vid omboot

```bash
crontab -e
```
Lägg till:
```
@reboot cd ~/agentindex && source venv/bin/activate && nohup python -m agentindex.run > agentindex.log 2>&1 &
```

---

## RAM-fördelning (16GB)

```
macOS              ~3 GB
OpenClaw           ~1 GB
Ollama (7B)        ~5 GB
PostgreSQL         ~0.5 GB
Redis + Nginx      ~0.2 GB
AgentIndex         ~0.5 GB
─────────────────────────
Totalt             ~10 GB
Ledigt             ~6 GB ✓
```

## Daglig drift

```bash
tail -20 ~/agentindex/agentindex.log
psql agentindex -c "SELECT source, count(*) FROM agents GROUP BY source;"
psql agentindex -c "SELECT crawl_status, count(*) FROM agents GROUP BY crawl_status;"
```

## Migration till 64GB-maskinen (senare)

```bash
# På gamla maskinen:
pg_dump agentindex > agentindex_backup.sql
# Kopiera ~/agentindex + backup till nya maskinen

# På nya maskinen:
psql agentindex < agentindex_backup.sql
ollama pull qwen2.5:72b
# Ändra .env: OLLAMA_MODEL_LARGE=qwen2.5:72b
python -m agentindex.run
```
