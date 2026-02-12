"""
AgentIndex Semantic Search

FAISS + sentence-transformers for vector-based agent discovery.
Replaces keyword matching with semantic understanding.

Usage:
    from agentindex.api.semantic import SemanticSearch
    search = SemanticSearch()
    search.build_index()  # once, or on schedule
    results = search.search("code review agent", top_k=10)
"""

import logging
import os
import time
import numpy as np
from typing import Optional
from datetime import datetime

logger = logging.getLogger("agentindex.semantic")

INDEX_DIR = os.path.expanduser("~/agentindex/semantic_index")
INDEX_PATH = os.path.join(INDEX_DIR, "agents.faiss")
IDS_PATH = os.path.join(INDEX_DIR, "agent_ids.npy")
META_PATH = os.path.join(INDEX_DIR, "index_meta.json")
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Singleton instance
_instance: Optional["SemanticSearch"] = None


def get_semantic_search() -> "SemanticSearch":
    """Get or create singleton SemanticSearch instance."""
    global _instance
    if _instance is None:
        _instance = SemanticSearch()
    return _instance


class SemanticSearch:

    def __init__(self):
        self.model = None
        self.index = None
        self.agent_ids = None
        self.index_size = 0
        self.last_built = None
        self._load_model()
        self._load_index()

    def _load_model(self):
        """Load sentence-transformer model."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {MODEL_NAME}")
            self.model = SentenceTransformer(MODEL_NAME)
            logger.info("Embedding model loaded")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")

    def _load_index(self):
        """Load existing FAISS index from disk."""
        if os.path.exists(INDEX_PATH) and os.path.exists(IDS_PATH):
            try:
                import faiss
                import json
                self.index = faiss.read_index(INDEX_PATH)
                self.agent_ids = np.load(IDS_PATH, allow_pickle=True)
                self.index_size = self.index.ntotal
                if os.path.exists(META_PATH):
                    with open(META_PATH) as f:
                        meta = json.load(f)
                        self.last_built = meta.get("built_at")
                logger.info(f"Loaded FAISS index: {self.index_size} vectors, built {self.last_built}")
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {e}")

    def build_index(self, batch_size: int = 500) -> dict:
        """Build FAISS index from all active agents in DB."""
        import faiss
        import json
        from agentindex.db.models import Agent, get_session
        from sqlalchemy import select

        logger.info("Building semantic index...")
        start = time.time()

        session = get_session()
        agents = session.execute(
            select(Agent.id, Agent.name, Agent.description, Agent.category,
                   Agent.capabilities, Agent.tags)
            .where(
                Agent.is_active == True,
                Agent.crawl_status.in_(["parsed", "classified", "ranked"]),
            )
        ).all()
        session.close()

        if not agents:
            logger.warning("No agents to index")
            return {"status": "empty", "count": 0}

        logger.info(f"Embedding {len(agents)} agents...")

        # Build text for each agent
        texts = []
        ids = []
        for agent in agents:
            agent_id, name, desc, category, capabilities, tags = agent
            text = self._build_agent_text(name, desc, category, capabilities, tags)
            texts.append(text)
            ids.append(str(agent_id))

        # Encode in batches
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
            all_embeddings.append(embeddings)
            if (i + batch_size) % 5000 == 0:
                logger.info(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

        embeddings_matrix = np.vstack(all_embeddings).astype("float32")

        # Build FAISS index (Inner Product = cosine similarity when normalized)
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        index.add(embeddings_matrix)

        # Save
        os.makedirs(INDEX_DIR, exist_ok=True)
        faiss.write_index(index, INDEX_PATH)
        np.save(IDS_PATH, np.array(ids))
        meta = {
            "built_at": datetime.utcnow().isoformat(),
            "agent_count": len(ids),
            "model": MODEL_NAME,
            "embedding_dim": EMBEDDING_DIM,
            "build_time_seconds": round(time.time() - start, 1),
        }
        with open(META_PATH, "w") as f:
            json.dump(meta, f, indent=2)

        # Update instance
        self.index = index
        self.agent_ids = np.array(ids)
        self.index_size = index.ntotal
        self.last_built = meta["built_at"]

        elapsed = round(time.time() - start, 1)
        logger.info(f"Semantic index built: {len(ids)} agents in {elapsed}s")
        return {"status": "ok", "count": len(ids), "time_seconds": elapsed}

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Semantic search — returns list of {agent_id, score}.
        Scores are cosine similarity (0.0 to 1.0).
        """
        if self.index is None or self.model is None:
            logger.warning("Semantic index not available, returning empty")
            return []

        if self.index.ntotal == 0:
            return []

        # Encode query
        query_vec = self.model.encode([query], normalize_embeddings=True).astype("float32")

        # Search
        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.agent_ids):
                continue
            results.append({
                "agent_id": self.agent_ids[idx],
                "score": float(score),
            })

        return results

    def _build_agent_text(self, name, desc, category, capabilities, tags) -> str:
        """Build embedding text from agent fields."""
        parts = []
        if name:
            parts.append(name)
        if desc:
            parts.append(desc[:500])  # Cap description length
        if category:
            parts.append(f"category: {category}")
        if capabilities:
            if isinstance(capabilities, list):
                parts.append("capabilities: " + ", ".join(str(c) for c in capabilities[:10]))
            elif isinstance(capabilities, dict):
                parts.append("capabilities: " + ", ".join(str(v) for v in list(capabilities.values())[:10]))
        if tags:
            if isinstance(tags, list):
                parts.append("tags: " + ", ".join(str(t) for t in tags[:10]))
        return " | ".join(parts)

    def get_status(self) -> dict:
        """Return current index status."""
        return {
            "index_loaded": self.index is not None,
            "model_loaded": self.model is not None,
            "index_size": self.index_size,
            "last_built": self.last_built,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/agentindex/.env"))
    search = SemanticSearch()
    result = search.build_index()
    print(f"\nBuild result: {result}")
    # Test search
    test_queries = ["code review agent", "data analysis", "security scanning", "writing assistant"]
    for q in test_queries:
        results = search.search(q, top_k=3)
        print(f"\n'{q}' -> {len(results)} results")
        for r in results:
            print(f"  {r['agent_id'][:8]}... score={r['score']:.3f}")
