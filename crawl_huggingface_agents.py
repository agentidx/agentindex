#!/usr/bin/env python3
"""
HuggingFace Agent-Focused Crawler
Filtrerar för AI agent-relevanta models enligt Anders spec:
- Tags: agent, tool-use, function-calling, chat, conversational, text-generation
- 100+ downloads minimum
- ALLA fine-tuned LLMs
"""

import requests
import time
import logging
from datetime import datetime
from agentindex.db.models import Agent, get_session
import uuid
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-agents] %(message)s")
logger = logging.getLogger("hf_agents")

class HuggingFaceAgentCrawler:
    def __init__(self):
        self.session = get_session()
        self.models_url = "https://huggingface.co/api/models"
        
        # Agent-relevanta tags (Anders spec)
        self.agent_tags = [
            'agent', 'tool-use', 'function-calling', 'chat', 
            'conversational', 'text-generation'
        ]
        
        # Agent-relevanta keywords i namn/beskrivning
        self.agent_keywords = [
            'agent', 'assistant', 'tool', 'function', 'chat', 'conversation',
            'langchain', 'autogen', 'crewai', 'openai', 'anthropic'
        ]
        
        self.headers = {
            'User-Agent': 'AgentIndex/1.0 - Agent Discovery',
            'Accept': 'application/json'
        }
    
    def is_agent_relevant(self, model: dict) -> bool:
        """Check if model is agent-relevant based on Anders criteria."""
        tags = model.get('tags', [])
        model_id = model.get('modelId', '').lower()
        description = (model.get('description') or '').lower()
        pipeline_tag = model.get('pipeline_tag', '').lower()
        downloads = model.get('downloads', 0)
        
        # Minimum downloads filter
        if downloads < 100:
            return False
        
        # Check for agent tags
        for tag in self.agent_tags:
            if tag in tags:
                logger.debug(f"✅ Agent tag found: {tag} in {model_id}")
                return True
        
        # Check pipeline tag for text-generation (potential agents)
        if pipeline_tag in ['text-generation', 'conversational']:
            logger.debug(f"✅ Agent pipeline: {pipeline_tag} in {model_id}")
            return True
        
        # Check for agent keywords in model name or description
        text_to_search = f"{model_id} {description}"
        for keyword in self.agent_keywords:
            if keyword in text_to_search:
                logger.debug(f"✅ Agent keyword: {keyword} in {model_id}")
                return True
        
        # ALLA fine-tuned LLMs (Anders requirement)
        if any(term in model_id for term in ['fine-tuned', 'ft-', 'lora', 'qlora', 'finetune']):
            logger.debug(f"✅ Fine-tuned LLM: {model_id}")
            return True
            
        return False
    
    def get_agent_models_page(self, offset: int = 0) -> list:
        """Get agent-relevant models with high download filter."""
        params = {
            'limit': 100,
            'offset': offset,
            'sort': 'downloads',
            'direction': -1,  # Descending (highest downloads first)
            'filter': 'text-generation'  # Start with text-generation models
        }
        
        try:
            response = requests.get(self.models_url, headers=self.headers, params=params)
            response.raise_for_status()
            models = response.json()
            
            # Filter for agent-relevance
            agent_models = []
            for model in models:
                if self.is_agent_relevant(model):
                    agent_models.append(model)
            
            logger.info(f"📊 Page offset {offset}: {len(models)} total → {len(agent_models)} agent-relevant")
            return agent_models
            
        except Exception as e:
            logger.error(f"Error fetching agent models: {e}")
            return []
    
    def model_to_agent(self, model: dict) -> dict:
        """Convert HuggingFace model to Agent format."""
        model_id = model.get('modelId', '')
        author = model_id.split('/')[0] if '/' in model_id else 'anonymous'
        name = model_id.split('/')[-1] if '/' in model_id else model_id
        
        tags = model.get('tags', [])
        if model.get('pipeline_tag'):
            tags.append(model.get('pipeline_tag'))
        
        return {
            'source': 'huggingface_agent',
            'source_url': f"https://huggingface.co/{model_id}",
            'source_id': model_id,
            'name': name,
            'description': model.get('description', ''),
            'author': author,
            'stars': model.get('likes', 0),
            'downloads': model.get('downloads', 0),
            'last_source_update': self._parse_date(model.get('lastModified')),
            'tags': tags[:8],
            'protocols': ['huggingface_api'],
            'raw_metadata': model,
            'first_indexed': datetime.now(),
            'last_crawled': datetime.now(),
            'crawl_status': 'indexed'
        }
    
    def _parse_date(self, date_str: str):
        """Parse HuggingFace date."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
    
    def crawl_agent_models(self, max_models: int = 5000):
        """Crawl agent-focused models."""
        logger.info(f"🤖 Starting agent-focused HuggingFace crawl (max {max_models} models)")
        
        new_count = 0
        updated_count = 0
        processed_count = 0
        offset = 0
        
        while processed_count < max_models:
            agent_models = self.get_agent_models_page(offset)
            
            if not agent_models:
                break
            
            for model in agent_models:
                try:
                    if processed_count >= max_models:
                        break
                        
                    agent_data = self.model_to_agent(model)
                    
                    existing = self.session.query(Agent).filter_by(
                        source='huggingface_agent',
                        source_id=agent_data['source_id']
                    ).first()
                    
                    if existing:
                        existing.last_crawled = datetime.now()
                        existing.downloads = agent_data['downloads']
                        existing.stars = agent_data['stars']
                        updated_count += 1
                    else:
                        agent = Agent(**agent_data)
                        agent.id = uuid.uuid4()
                        self.session.add(agent)
                        new_count += 1
                    
                    processed_count += 1
                    
                    if processed_count % 50 == 0:
                        self.session.commit()
                        logger.info(f"💾 Processed {processed_count}: {new_count} new, {updated_count} updated")
                    
                except Exception as e:
                    logger.error(f"Error processing {model.get('modelId')}: {e}")
                    continue
            
            offset += 100
            time.sleep(1)  # Rate limiting
        
        self.session.commit()
        logger.info(f"🎯 Agent-focused crawl complete: {new_count} new agents, {updated_count} updated")
        return {'new': new_count, 'updated': updated_count, 'total_processed': processed_count}

if __name__ == "__main__":
    crawler = HuggingFaceAgentCrawler()
    result = crawler.crawl_agent_models(5000)  # Test batch of 5000
    print(f"Agent-focused results: {result}")