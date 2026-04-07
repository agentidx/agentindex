#!/usr/bin/env python3
"""Massive npm crawler - 300+ search terms, paginated, deduped"""
import requests, time, logging, uuid, psycopg2, psycopg2.extras, json, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [npm-massive] %(message)s",
    handlers=[logging.FileHandler(f'npm_massive_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("npm-massive")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

# 300+ search terms covering all AI/ML niches
SEARCH_TERMS = [
    # Core AI
    "ai-agent", "llm-agent", "ai-assistant", "chatbot", "conversational-ai",
    "ai-tool", "ai-framework", "ai-sdk", "ai-api", "ai-service",
    "ai-platform", "ai-engine", "ai-model", "ai-pipeline", "ai-workflow",
    # LLM specific
    "llm", "large-language-model", "gpt", "gpt-4", "gpt-3", "chatgpt",
    "openai", "anthropic", "claude", "gemini", "mistral", "llama",
    "groq", "together-ai", "replicate", "fireworks-ai", "perplexity",
    "cohere", "ai21", "deepseek", "qwen", "phi", "ollama",
    # Agent frameworks
    "langchain", "langgraph", "crewai", "autogen", "multi-agent",
    "autonomous-agent", "agent-framework", "agentic", "agent-orchestration",
    "agent-runtime", "agent-protocol", "agent-sdk", "agent-toolkit",
    "swarm", "magentic-one", "semantic-kernel", "haystack",
    "llamaindex", "llama-index", "dspy", "instructor",
    # MCP
    "mcp-server", "mcp-client", "mcp-tool", "model-context-protocol",
    "mcp-sdk", "mcp-transport", "mcp-stdio", "mcp-sse",
    # RAG and Vector
    "rag", "retrieval-augmented", "vector-db", "vector-store",
    "vector-search", "vector-embedding", "embedding", "embeddings",
    "pinecone", "weaviate", "chromadb", "chroma", "qdrant", "milvus",
    "faiss", "pgvector", "supabase-vector", "semantic-search",
    # Prompt engineering
    "prompt", "prompt-engineering", "prompt-template", "prompt-chain",
    "chain-of-thought", "few-shot", "prompt-optimization", "prompt-testing",
    "guardrail", "ai-safety", "content-moderation", "ai-moderation",
    # ML frameworks
    "tensorflow", "pytorch", "torch", "keras", "scikit-learn", "sklearn",
    "transformers", "huggingface", "hugging-face", "diffusers",
    "accelerate", "peft", "trl", "datasets-ml",
    # Training and inference
    "fine-tuning", "fine-tune", "lora", "qlora", "training-ml",
    "inference", "model-serving", "model-deployment", "onnx",
    "tensorrt", "triton", "vllm", "tgi", "mlflow", "wandb",
    "experiment-tracking", "model-registry", "mlops",
    # NLP
    "nlp", "natural-language", "text-generation", "text-analysis",
    "sentiment-analysis", "named-entity", "ner", "tokenizer",
    "text-classification", "text-summarization", "translation-ai",
    "question-answering", "text-embedding", "spell-check-ai",
    # Computer Vision
    "computer-vision", "image-recognition", "object-detection",
    "image-classification", "image-segmentation", "face-detection",
    "face-recognition", "ocr", "optical-character", "image-generation",
    "stable-diffusion", "dall-e", "midjourney", "flux-ai",
    "image-to-text", "text-to-image", "video-ai", "video-generation",
    # Speech and Audio
    "text-to-speech", "tts", "speech-to-text", "stt", "whisper",
    "voice-ai", "voice-assistant", "speech-recognition", "audio-ai",
    "voice-clone", "voice-synthesis", "transcription",
    # Code AI
    "code-generation", "code-ai", "copilot", "code-assistant",
    "code-completion", "code-review-ai", "code-analysis",
    "ai-coding", "pair-programming", "code-interpreter",
    # Data and Analytics
    "data-science", "data-analysis", "data-pipeline",
    "data-extraction", "data-labeling", "data-annotation",
    "data-cleaning", "data-augmentation", "synthetic-data",
    "feature-engineering", "automl", "auto-ml",
    # Automation
    "ai-automation", "workflow-automation", "rpa", "robotic-process",
    "task-automation", "ai-workflow", "process-automation",
    "browser-automation-ai", "web-scraping-ai", "ai-scraper",
    # Domain specific
    "medical-ai", "healthcare-ai", "clinical-ai", "biomedical-ai",
    "legal-ai", "law-ai", "contract-ai", "compliance-ai",
    "finance-ai", "trading-ai", "fintech-ai", "risk-ai",
    "education-ai", "edtech-ai", "tutoring-ai",
    "marketing-ai", "seo-ai", "content-ai", "copywriting-ai",
    "customer-service-ai", "support-ai", "helpdesk-ai",
    "sales-ai", "crm-ai", "lead-generation-ai",
    "hr-ai", "recruiting-ai", "resume-ai",
    "gaming-ai", "game-ai", "npc-ai",
    "music-ai", "art-ai", "creative-ai", "design-ai",
    # Security
    "ai-security", "adversarial", "red-team-ai", "ai-firewall",
    "prompt-injection", "jailbreak-detection", "ai-governance",
    "responsible-ai", "explainable-ai", "xai", "ai-ethics",
    "ai-audit", "model-monitoring", "drift-detection",
    # Infrastructure
    "gpu-cloud", "model-hosting", "ai-infrastructure",
    "model-cache", "ai-gateway", "ai-proxy", "ai-router",
    "ai-load-balancer", "token-counter", "cost-tracking-ai",
    # Specific tools
    "openai-sdk", "anthropic-sdk", "google-ai", "vertex-ai",
    "bedrock", "sagemaker", "azure-ai", "cognitive-services",
    "palm", "bard", "claude-sdk", "gemini-sdk",
    # Knowledge and Memory
    "knowledge-graph", "knowledge-base", "ai-memory",
    "long-term-memory", "conversation-memory", "context-window",
    "document-ai", "document-processing", "pdf-ai", "ocr-ai",
    # Evaluation
    "llm-eval", "ai-evaluation", "benchmark", "ai-testing",
    "ai-quality", "hallucination-detection", "factcheck",
    "ai-observability", "tracing-ai", "langsmith", "langfuse",
    # Multimodal
    "multimodal", "multi-modal", "vision-language", "vlm",
    "image-text", "audio-text", "video-text",
    # Robotics
    "robotics-ai", "robot-framework", "ros-ai", "drone-ai",
    "autonomous-driving", "self-driving", "navigation-ai",
    # Misc AI
    "recommendation", "recommender", "personalization-ai",
    "search-ai", "ai-search", "neural-search",
    "time-series-ai", "forecasting-ai", "prediction-ai",
    "anomaly-detection-ai", "fraud-detection-ai",
    "graph-neural", "gnn", "reinforcement-learning", "rl-agent",
    "federated-learning", "differential-privacy-ai",
    "quantum-ml", "quantum-ai",
]

def search_npm(query, offset=0, size=250):
    """Search npm registry. Max 250 results per query."""
    try:
        r = requests.get(
            f"https://registry.npmjs.org/-/v1/search",
            params={"text": query, "size": size, "from": offset},
            headers={"User-Agent": "NerqCrawler/1.0"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("objects", []), data.get("total", 0)
        elif r.status_code == 429:
            logger.warning(f"Rate limited on '{query}', sleeping 30s...")
            time.sleep(30)
            return [], 0
        else:
            logger.warning(f"HTTP {r.status_code} for '{query}'")
            return [], 0
    except Exception as e:
        logger.error(f"Error searching '{query}': {e}")
        return [], 0

def parse_package(obj):
    """Parse npm search result into agent dict."""
    pkg = obj.get("package", {})
    name = pkg.get("name", "")
    if not name:
        return None
    return {
        "source": "npm_full",
        "source_url": f"https://www.npmjs.com/package/{name}",
        "source_id": name,
        "name": name,
        "description": (pkg.get("description") or "")[:2000],
        "author": (pkg.get("publisher", {}).get("username") or
                   (pkg.get("maintainers", [{}])[0].get("username") if pkg.get("maintainers") else None) or
                   "unknown"),
        "tags": (pkg.get("keywords") or [])[:10],
        "downloads": obj.get("downloads", {}).get("monthly", 0),
        "version": pkg.get("version", ""),
        "updated": pkg.get("date", ""),
    }

def insert_batch(agents):
    """Insert batch with ON CONFLICT DO NOTHING."""
    if not agents:
        return 0
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    vals = []
    seen = set()
    for a in agents:
        u = a["source_url"]
        if u in seen:
            continue
        seen.add(u)
        vals.append((
            str(uuid.uuid4()), a["source"], u, a["source_id"], a["name"][:500],
            a.get("description", "")[:2000], a.get("author", "unknown")[:255],
            0, a.get("downloads", 0), a.get("tags", [])[:10], [],
            json.dumps(a), datetime.now(), datetime.now(), True, "indexed"
        ))
    inserted = 0
    if vals:
        try:
            psycopg2.extras.execute_values(cur,
                """INSERT INTO agents (id, source, source_url, source_id, name, description, author,
                   stars, downloads, tags, protocols, raw_metadata, first_indexed, last_crawled,
                   is_active, crawl_status) VALUES %s ON CONFLICT (source_url) DO NOTHING""",
                vals, page_size=500)
            inserted = cur.rowcount
            conn.commit()
        except Exception as e:
            logger.error(f"Insert error: {e}")
            conn.rollback()
    cur.close()
    conn.close()
    return inserted

def main():
    logger.info(f"=== npm Massive Crawler ===")
    logger.info(f"Search terms: {len(SEARCH_TERMS)}")

    total_found = 0
    total_inserted = 0
    seen_names = set()

    for i, term in enumerate(SEARCH_TERMS):
        logger.info(f"[{i+1}/{len(SEARCH_TERMS)}] Searching: '{term}'")

        # First page
        objects, total = search_npm(term)
        if not objects:
            time.sleep(0.5)
            continue

        logger.info(f"  Found {total} total results for '{term}'")

        # Parse and dedupe
        batch = []
        for obj in objects:
            parsed = parse_package(obj)
            if parsed and parsed["name"] not in seen_names:
                seen_names.add(parsed["name"])
                batch.append(parsed)

        # Paginate if more than 250
        offset = 250
        while offset < min(total, 1000):  # npm caps at ~1000
            more_objects, _ = search_npm(term, offset=offset)
            if not more_objects:
                break
            for obj in more_objects:
                parsed = parse_package(obj)
                if parsed and parsed["name"] not in seen_names:
                    seen_names.add(parsed["name"])
                    batch.append(parsed)
            offset += 250
            time.sleep(0.3)

        # Insert
        if batch:
            inserted = insert_batch(batch)
            total_found += len(batch)
            total_inserted += inserted
            logger.info(f"  New: {len(batch)}, Inserted: {inserted}")

        # Be polite
        time.sleep(0.5)

        # Progress every 25 terms
        if (i + 1) % 25 == 0:
            logger.info(f"=== Progress: {i+1}/{len(SEARCH_TERMS)} terms, {total_found:,} found, {total_inserted:,} inserted ===")

    logger.info(f"=== DONE === Found: {total_found:,}, Inserted: {total_inserted:,}, Unique packages: {len(seen_names):,}")

if __name__ == "__main__":
    main()
