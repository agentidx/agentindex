"""
HuggingFace Spider - EXPANDED for 500K Scale

MASSIVE expansion targeting HuggingFace's 500K+ models, 200K+ spaces, 100K+ datasets.
Current: 1,519 agents → Target: 20K-50K+ agents (15-30x expansion)

Strategy:
1. Expanded model search (all AI/ML model types)  
2. Spaces discovery (hosted AI apps)
3. Datasets with associated models
4. Pipeline/task-based discovery
5. Organization-based crawling (meta, microsoft, google, etc.)
"""

import time
import logging
from datetime import datetime
from typing import Optional, List, Dict
import httpx
from agentindex.db.models import Agent, CrawlJob, get_session
from sqlalchemy import select

logger = logging.getLogger("agentindex.spiders.huggingface_expanded")

HF_API_URL = "https://huggingface.co/api"

# MASSIVELY EXPANDED search queries
EXPANDED_MODEL_QUERIES = [
    # Original core terms
    "agent", "mcp", "autonomous", "tool-use", "function-calling", "assistant", "multi-agent", "agentic",
    
    # LLM & Language Models
    "llm", "language-model", "gpt", "bert", "t5", "roberta", "deberta", "claude", "llama", "mistral",
    "chat", "conversation", "instruction", "dialogue", "qa", "question-answering",
    
    # Specific capabilities
    "code-generation", "text-generation", "summarization", "translation", "sentiment-analysis",
    "classification", "ner", "entity-recognition", "text-classification", "zero-shot",
    
    # Vision & Multimodal
    "vision", "image-classification", "object-detection", "image-generation", "diffusion",
    "clip", "vilt", "blip", "multimodal", "vision-language", "image-captioning",
    
    # Audio & Speech  
    "speech", "audio", "tts", "text-to-speech", "speech-recognition", "asr", "wav2vec",
    "audio-classification", "music", "voice", "whisper",
    
    # Task-specific
    "rag", "retrieval", "embedding", "similarity", "search", "recommendation",
    "planning", "reasoning", "logic", "math", "science", "coding",
    
    # Domain-specific
    "medical", "legal", "finance", "education", "customer-service", "writing",
    "research", "analysis", "data-science", "business", "marketing",
]

EXPANDED_SPACE_QUERIES = [
    # Original core terms  
    "ai-agent", "agent", "mcp-server", "assistant", "autonomous", "tool",
    
    # Interactive AI apps
    "chatbot", "chat", "demo", "playground", "interface", "webapp", "app",
    "gradio", "streamlit", "interactive", "ui", "gui", "web-app",
    
    # Specific AI applications
    "text-generation", "image-generation", "code-generation", "writing",
    "summarization", "translation", "qa", "question-answering", "search",
    "analysis", "classification", "detection", "recognition",
    
    # Tools and utilities
    "api", "service", "microservice", "pipeline", "workflow", "automation",
    "data-processing", "preprocessing", "visualization", "dashboard",
    
    # Domain applications
    "research", "education", "business", "productivity", "creativity",
    "healthcare", "finance", "legal", "customer-service", "support",
]

DATASET_QUERIES = [
    # Datasets that often have associated models
    "instruction", "chat", "conversation", "dialogue", "qa", "question-answer",
    "code", "programming", "text-generation", "summarization", "translation",
    "classification", "sentiment", "ner", "entity", "reasoning", "math",
]

# High-value organizations to crawl exhaustively  
PRIORITY_ORGANIZATIONS = [
    "microsoft", "google", "meta", "facebook", "openai", "anthropic", "cohere",
    "mistralai", "stabilityai", "huggingface", "bigscience", "eleutherai",
    "allenai", "nvidia", "intel", "apple", "adobe", "salesforce", "ibm",
    "deepmind", "uber", "twitter", "amazon", "baidu", "tencent", "bytedance",
]

# Task categories for comprehensive coverage
HF_TASKS = [
    "text-generation", "text-classification", "token-classification", "question-answering",
    "summarization", "translation", "text2text-generation", "fill-mask", 
    "sentence-similarity", "conversational", "text-to-speech", "automatic-speech-recognition",
    "audio-classification", "image-classification", "object-detection", "image-segmentation",
    "text-to-image", "image-to-text", "visual-question-answering", "document-question-answering",
    "table-question-answering", "feature-extraction", "zero-shot-classification",
]

class HuggingFaceExpandedSpider:
    """EXPANDED HuggingFace crawler for massive coverage."""

    def __init__(self):
        self.client = httpx.Client(timeout=30)
        self.session = get_session()
        self.seen_items = set()  # Track duplicates
        
    def crawl_expanded(self, max_results_per_query: int = 100) -> Dict:
        """Main expanded crawl method."""
        start_time = time.time()
        logger.info("🚀 Starting EXPANDED HuggingFace crawl")
        logger.info(f"Target: 20K-50K+ agents (vs current 1,519)")
        
        stats = {
            "models_found": 0, "models_new": 0,
            "spaces_found": 0, "spaces_new": 0, 
            "datasets_found": 0, "datasets_new": 0,
            "orgs_crawled": 0, "tasks_crawled": 0,
            "errors": 0, "source": "huggingface_expanded"
        }

        # Phase 1: Expanded model search
        logger.info("🤖 Phase 1: Expanded model search...")
        for i, query in enumerate(EXPANDED_MODEL_QUERIES, 1):
            try:
                result = self._crawl_models_expanded(query, max_results_per_query)
                stats["models_found"] += result["found"]
                stats["models_new"] += result["new"]
                
                if i % 10 == 0:
                    logger.info(f"📊 Model search progress: {i}/{len(EXPANDED_MODEL_QUERIES)}, {stats['models_found']} found")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Model query '{query}' failed: {e}")
                stats["errors"] += 1

        # Phase 2: Expanded spaces search  
        logger.info("🌌 Phase 2: Expanded spaces search...")
        for query in EXPANDED_SPACE_QUERIES:
            try:
                result = self._crawl_spaces_expanded(query, max_results_per_query)
                stats["spaces_found"] += result["found"]
                stats["spaces_new"] += result["new"]
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Spaces query '{query}' failed: {e}")
                stats["errors"] += 1

        # Phase 3: Dataset search (with associated models)
        logger.info("📊 Phase 3: Dataset search...")  
        for query in DATASET_QUERIES:
            try:
                result = self._crawl_datasets_expanded(query, max_results_per_query)
                stats["datasets_found"] += result["found"]
                stats["datasets_new"] += result["new"]
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Dataset query '{query}' failed: {e}")
                stats["errors"] += 1

        # Phase 4: Organization-based crawling
        logger.info("🏢 Phase 4: Organization crawling...")
        for org in PRIORITY_ORGANIZATIONS[:10]:  # Limit to top 10 to avoid overload
            try:
                result = self._crawl_organization(org, max_results_per_query)
                stats["models_found"] += result.get("models", 0)
                stats["spaces_found"] += result.get("spaces", 0) 
                stats["orgs_crawled"] += 1
                time.sleep(1)  # More conservative for org crawling
                
            except Exception as e:
                logger.error(f"Organization '{org}' failed: {e}")
                stats["errors"] += 1

        # Phase 5: Task-based discovery  
        logger.info("📋 Phase 5: Task-based discovery...")
        for task in HF_TASKS[:15]:  # Limit to most important tasks
            try:
                result = self._crawl_task_models(task, max_results_per_query)
                stats["models_found"] += result["found"]
                stats["models_new"] += result["new"]
                stats["tasks_crawled"] += 1
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Task '{task}' failed: {e}")
                stats["errors"] += 1

        end_time = time.time()
        duration = end_time - start_time
        
        total_found = stats["models_found"] + stats["spaces_found"] + stats["datasets_found"]
        total_new = stats["models_new"] + stats["spaces_new"] + stats["datasets_new"]
        
        stats.update({
            "total_found": total_found,
            "total_new": total_new,
            "duration_seconds": round(duration, 2),
            "items_per_second": round(total_found / duration, 2) if duration > 0 else 0,
            "unique_items": len(self.seen_items)
        })
        
        logger.info("🎯 EXPANDED HuggingFace crawl completed!")
        logger.info(f"   Models: {stats['models_found']:,} ({stats['models_new']} new)")
        logger.info(f"   Spaces: {stats['spaces_found']:,} ({stats['spaces_new']} new)")  
        logger.info(f"   Datasets: {stats['datasets_found']:,} ({stats['datasets_new']} new)")
        logger.info(f"   Total: {total_found:,} items, {total_new:,} new")
        logger.info(f"   Duration: {duration:.1f}s")
        
        return stats

    def _crawl_models_expanded(self, query: str, max_results: int) -> Dict:
        """Expanded model search with better filtering."""
        stats = {"found": 0, "new": 0}
        
        try:
            url = f"{HF_API_URL}/models"
            params = {"search": query, "limit": max_results, "full": "true"}
            
            response = self.client.get(url, params=params)
            if response.status_code != 200:
                return stats
                
            models = response.json()
            
            for model in models:
                model_id = model.get("modelId", model.get("id", ""))
                if not model_id or model_id in self.seen_items:
                    continue
                    
                self.seen_items.add(model_id)
                
                # Enhanced filtering
                if self._is_relevant_model(model):
                    result = self._process_hf_item(model, "model")
                    if result == "new":
                        stats["new"] += 1
                    stats["found"] += 1
                    
        except Exception as e:
            logger.error(f"Model search error for '{query}': {e}")
            
        return stats

    def _crawl_spaces_expanded(self, query: str, max_results: int) -> Dict:
        """Expanded spaces search."""
        stats = {"found": 0, "new": 0}
        
        try:
            url = f"{HF_API_URL}/spaces"
            params = {"search": query, "limit": max_results, "full": "true"}
            
            response = self.client.get(url, params=params)
            if response.status_code != 200:
                return stats
                
            spaces = response.json()
            
            for space in spaces:
                space_id = space.get("id", "")
                if not space_id or space_id in self.seen_items:
                    continue
                    
                self.seen_items.add(space_id)
                
                result = self._process_hf_item(space, "space")
                if result == "new":
                    stats["new"] += 1
                stats["found"] += 1
                    
        except Exception as e:
            logger.error(f"Spaces search error for '{query}': {e}")
            
        return stats

    def _crawl_datasets_expanded(self, query: str, max_results: int) -> Dict:
        """Search datasets (many have associated models)."""
        stats = {"found": 0, "new": 0}
        
        try:
            url = f"{HF_API_URL}/datasets"
            params = {"search": query, "limit": max_results}
            
            response = self.client.get(url, params=params)
            if response.status_code != 200:
                return stats
                
            datasets = response.json()
            
            for dataset in datasets:
                dataset_id = dataset.get("id", "")
                if not dataset_id or dataset_id in self.seen_items:
                    continue
                    
                self.seen_items.add(dataset_id)
                
                # Only include datasets that are tool/model-relevant
                if self._is_relevant_dataset(dataset):
                    result = self._process_hf_item(dataset, "dataset")
                    if result == "new":
                        stats["new"] += 1
                    stats["found"] += 1
                    
        except Exception as e:
            logger.error(f"Dataset search error for '{query}': {e}")
            
        return stats

    def _crawl_organization(self, org: str, max_results: int) -> Dict:
        """Crawl all models and spaces from a high-value organization."""
        stats = {"models": 0, "spaces": 0}
        
        try:
            # Get org models
            models_url = f"{HF_API_URL}/models"
            models_response = self.client.get(models_url, params={"author": org, "limit": max_results})
            if models_response.status_code == 200:
                models = models_response.json()
                for model in models:
                    model_id = model.get("modelId", model.get("id", ""))
                    if model_id and model_id not in self.seen_items:
                        self.seen_items.add(model_id)
                        self._process_hf_item(model, "model")
                        stats["models"] += 1
            
            # Get org spaces
            spaces_url = f"{HF_API_URL}/spaces"  
            spaces_response = self.client.get(spaces_url, params={"author": org, "limit": max_results})
            if spaces_response.status_code == 200:
                spaces = spaces_response.json()
                for space in spaces:
                    space_id = space.get("id", "")
                    if space_id and space_id not in self.seen_items:
                        self.seen_items.add(space_id)
                        self._process_hf_item(space, "space")
                        stats["spaces"] += 1
                        
        except Exception as e:
            logger.error(f"Organization crawl error for '{org}': {e}")
            
        return stats

    def _crawl_task_models(self, task: str, max_results: int) -> Dict:
        """Crawl models by task category."""
        stats = {"found": 0, "new": 0}
        
        try:
            url = f"{HF_API_URL}/models"
            params = {"pipeline_tag": task, "limit": max_results}
            
            response = self.client.get(url, params=params)
            if response.status_code != 200:
                return stats
                
            models = response.json()
            
            for model in models:
                model_id = model.get("modelId", model.get("id", ""))
                if not model_id or model_id in self.seen_items:
                    continue
                    
                self.seen_items.add(model_id)
                
                result = self._process_hf_item(model, "model")
                if result == "new":
                    stats["new"] += 1
                stats["found"] += 1
                    
        except Exception as e:
            logger.error(f"Task search error for '{task}': {e}")
            
        return stats

    def _is_relevant_model(self, model: Dict) -> bool:
        """Enhanced relevance filtering for models."""
        # Get text to analyze
        model_id = model.get("modelId", model.get("id", "")).lower()
        description = (model.get("description") or "").lower()
        tags = [tag.lower() for tag in model.get("tags", [])]
        
        # AI/ML relevance keywords
        relevant_keywords = [
            "ai", "agent", "assistant", "chat", "conversation", "dialogue",
            "llm", "language", "gpt", "bert", "t5", "generation", "text",
            "vision", "multimodal", "embedding", "classification", "detection",
            "rag", "retrieval", "tool", "function", "reasoning", "planning"
        ]
        
        # Check if any relevant keywords appear
        text_content = f"{model_id} {description} {' '.join(tags)}"
        return any(keyword in text_content for keyword in relevant_keywords)

    def _is_relevant_dataset(self, dataset: Dict) -> bool:
        """Filter for datasets that are tool/model relevant."""
        dataset_id = dataset.get("id", "").lower() 
        description = (dataset.get("description") or "").lower()
        tags = [tag.lower() for tag in dataset.get("tags", [])]
        
        # Focus on instruction/tool datasets
        relevant_keywords = [
            "instruction", "chat", "conversation", "dialogue", "tool", "function",
            "agent", "assistant", "code", "reasoning", "qa", "question"
        ]
        
        text_content = f"{dataset_id} {description} {' '.join(tags)}"
        return any(keyword in text_content for keyword in relevant_keywords)

    def _process_hf_item(self, item: Dict, item_type: str) -> str:
        """Process and save HuggingFace item (model/space/dataset)."""
        try:
            item_id = item.get("modelId", item.get("id", ""))
            if not item_id:
                return "error"
                
            # Check if exists
            hf_url = f"https://huggingface.co/{item_id}"
            existing = self.session.execute(
                select(Agent).where(Agent.source_url == hf_url)
            ).scalar_one_or_none()
            
            # Prepare agent data
            agent_data = {
                "name": item_id,
                "description": item.get("description", ""),
                "source": f"huggingface_{item_type}",
                "source_url": hf_url,
                "stars": item.get("likes", 0),
                "last_source_update": item.get("lastModified"),
                "raw_metadata": {
                    "huggingface_expanded": True,
                    "item_type": item_type,
                    "tags": item.get("tags", []),
                    "downloads": item.get("downloads", 0),
                    "pipeline_tag": item.get("pipeline_tag"),
                    "library_name": item.get("library_name"),
                    "author": item.get("author"),
                    "private": item.get("private", False),
                    "created_at": item.get("createdAt"),
                    "last_modified": item.get("lastModified")
                }
            }
            
            if existing:
                # Update existing
                for key, value in agent_data.items():
                    if key != "raw_metadata":
                        setattr(existing, key, value)
                    else:
                        existing_meta = existing.raw_metadata or {}
                        existing_meta.update(value)
                        existing.raw_metadata = existing_meta
                
                self.session.commit()
                return "updated"
            else:
                # Create new
                agent = Agent(**agent_data)
                self.session.add(agent)
                self.session.commit()
                return "new"
                
        except Exception as e:
            logger.error(f"Error processing {item_type} {item.get('id', 'unknown')}: {e}")
            self.session.rollback()
            return "error"

# Test function
def test_expanded_crawler():
    """Test the expanded HuggingFace crawler."""
    spider = HuggingFaceExpandedSpider()
    
    print(f"🧪 Testing HuggingFace expanded crawler")
    print(f"📊 Search queries: {len(EXPANDED_MODEL_QUERIES)} models, {len(EXPANDED_SPACE_QUERIES)} spaces")
    print(f"🏢 Priority orgs: {len(PRIORITY_ORGANIZATIONS)} organizations") 
    print(f"📋 HF tasks: {len(HF_TASKS)} task categories")
    print(f"🎯 Expected: 20K-50K+ agents (vs current 1,519)")
    
    # Would run: spider.crawl_expanded(max_results_per_query=50)

if __name__ == "__main__":
    test_expanded_crawler()