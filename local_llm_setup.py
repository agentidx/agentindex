"""
Local LLM Setup and Optimization for AgentIndex
Uses Ollama for local inference to reduce Anthropic costs
Budget optimization: $10 USD per day constraint
"""

import subprocess
import json
import requests
import os
from typing import Dict, List, Optional, Union
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalLLMManager:
    def __init__(self):
        self.ollama_url = "http://localhost:11434"
        self.available_models = []
        self.cost_savings = 0.0
        self.local_calls = 0
        
    def check_ollama_status(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.ollama_url}/api/version", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def install_ollama(self) -> bool:
        """Install Ollama if not present"""
        try:
            # Check if ollama is already installed
            result = subprocess.run(["which", "ollama"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Ollama already installed")
                return True
            
            # Install via homebrew
            logger.info("Installing Ollama via Homebrew...")
            subprocess.run(["brew", "install", "ollama"], check=True)
            
            # Start Ollama service
            subprocess.Popen(["ollama", "serve"])
            logger.info("Ollama installed and started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install Ollama: {e}")
            return False
    
    def download_recommended_models(self) -> bool:
        """Download recommended models for different tasks"""
        recommended_models = [
            "llama3.2:3b",      # Fast, good for simple tasks
            "codellama:7b",     # Code generation and analysis  
            "llama3.2:8b",      # Better reasoning, still efficient
            "qwen2.5-coder:7b", # Excellent coding model
        ]
        
        if not self.check_ollama_status():
            logger.error("Ollama not running. Starting...")
            if not self.start_ollama():
                return False
        
        success = True
        for model in recommended_models:
            try:
                logger.info(f"Downloading {model}...")
                subprocess.run(["ollama", "pull", model], check=True, timeout=300)
                logger.info(f"✅ {model} downloaded successfully")
            except Exception as e:
                logger.error(f"❌ Failed to download {model}: {e}")
                success = False
        
        self.refresh_available_models()
        return success
    
    def start_ollama(self) -> bool:
        """Start Ollama service"""
        try:
            # Check if already running
            if self.check_ollama_status():
                return True
            
            # Start in background
            subprocess.Popen(["ollama", "serve"])
            
            # Wait a bit for startup
            import time
            time.sleep(3)
            
            return self.check_ollama_status()
        except Exception as e:
            logger.error(f"Failed to start Ollama: {e}")
            return False
    
    def refresh_available_models(self) -> List[str]:
        """Get list of available models"""
        try:
            if not self.check_ollama_status():
                return []
                
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                models_data = response.json()
                self.available_models = [model['name'] for model in models_data.get('models', [])]
                return self.available_models
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
        
        return []
    
    def generate_local(self, prompt: str, model: str = "llama3.2:3b", 
                      system_prompt: str = "", max_tokens: int = 1000) -> Optional[Dict]:
        """Generate response using local LLM"""
        try:
            if model not in self.available_models:
                logger.warning(f"Model {model} not available locally")
                return None
            
            payload = {
                "model": model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.1
                }
            }
            
            response = requests.post(f"{self.ollama_url}/api/generate", 
                                   json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                self.local_calls += 1
                
                # Estimate cost savings vs Claude
                estimated_claude_cost = self._estimate_claude_cost(prompt, result.get('response', ''))
                self.cost_savings += estimated_claude_cost
                
                return {
                    "response": result.get('response', ''),
                    "model": model,
                    "local": True,
                    "tokens_used": result.get('eval_count', 0),
                    "cost_saved": estimated_claude_cost,
                    "time_taken": result.get('total_duration', 0) / 1e9  # Convert to seconds
                }
            else:
                logger.error(f"Local generation failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Local generation error: {e}")
            return None
    
    def _estimate_claude_cost(self, prompt: str, response: str) -> float:
        """Estimate what this would cost with Claude"""
        # Rough token estimation (1 token ≈ 0.75 words)
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(response.split()) * 1.3
        
        # Claude Sonnet pricing
        cost = (input_tokens * 0.000003) + (output_tokens * 0.000015)
        return cost
    
    def get_best_model_for_task(self, task_type: str) -> str:
        """Get recommended model for specific task"""
        task_models = {
            "code_generation": "qwen2.5-coder:7b",
            "code_analysis": "codellama:7b", 
            "simple_text": "llama3.2:3b",
            "reasoning": "llama3.2:8b",
            "data_processing": "llama3.2:3b",
            "documentation": "llama3.2:8b",
            "classification": "llama3.2:3b"
        }
        
        recommended = task_models.get(task_type, "llama3.2:3b")
        
        # Fallback to available model if recommended not available
        if recommended not in self.available_models and self.available_models:
            return self.available_models[0]
        
        return recommended
    
    def should_use_local(self, task_type: str, complexity: str = "medium") -> bool:
        """Decide whether to use local LLM or Claude API"""
        # Always use local for these tasks
        local_preferred = [
            "code_generation",
            "simple_text", 
            "data_processing",
            "classification",
            "documentation"
        ]
        
        # Use Claude for complex reasoning and critical tasks
        claude_preferred = [
            "complex_reasoning",
            "critical_analysis", 
            "user_facing_responses",
            "marketing_content"
        ]
        
        if task_type in local_preferred:
            return True
        elif task_type in claude_preferred:
            return False
        else:
            # For other tasks, decide based on complexity
            return complexity in ["simple", "medium"]
    
    def get_optimization_stats(self) -> Dict:
        """Get local LLM usage and optimization stats"""
        return {
            "local_calls": self.local_calls,
            "total_cost_saved": round(self.cost_savings, 4),
            "available_models": len(self.available_models),
            "ollama_status": "running" if self.check_ollama_status() else "stopped",
            "models_list": self.available_models
        }

# Smart prompt optimizer
class PromptOptimizer:
    """Optimize prompts to reduce token usage while maintaining quality"""
    
    @staticmethod
    def compress_prompt(prompt: str, max_length: int = 2000) -> str:
        """Compress prompt while keeping essential information"""
        if len(prompt) <= max_length:
            return prompt
        
        # Remove redundant words and phrases
        replacements = [
            ("please", ""),
            ("could you", ""),
            ("I would like you to", ""),
            ("  ", " "),  # Double spaces
        ]
        
        compressed = prompt
        for old, new in replacements:
            compressed = compressed.replace(old, new)
        
        # If still too long, truncate intelligently
        if len(compressed) > max_length:
            # Keep beginning and end, remove middle
            start = compressed[:max_length//2]
            end = compressed[-(max_length//2):]
            compressed = start + "\n[...content truncated...]\n" + end
        
        return compressed.strip()
    
    @staticmethod 
    def batch_similar_requests(requests: List[str]) -> str:
        """Batch similar requests into one API call"""
        if len(requests) <= 1:
            return requests[0] if requests else ""
        
        batched = f"Process these {len(requests)} similar requests:\n\n"
        for i, req in enumerate(requests, 1):
            batched += f"{i}. {req}\n"
        
        batched += "\nProvide numbered responses for each."
        return batched

if __name__ == "__main__":
    # Setup and test local LLM
    llm = LocalLLMManager()
    
    print("🚀 Setting up Local LLM for cost optimization...")
    print(f"Budget constraint: $10 USD per day")
    print()
    
    # Check/install Ollama
    if not llm.check_ollama_status():
        print("Installing Ollama...")
        if llm.install_ollama():
            print("✅ Ollama installed")
        else:
            print("❌ Ollama installation failed")
            exit(1)
    else:
        print("✅ Ollama already running")
    
    # Download models
    print("\nDownloading recommended models...")
    if llm.download_recommended_models():
        print("✅ Models downloaded")
    else:
        print("⚠️ Some models failed to download")
    
    # Test local generation
    print("\nTesting local generation...")
    result = llm.generate_local(
        "Write a simple Python function to add two numbers.",
        model="qwen2.5-coder:7b",
        system_prompt="You are a helpful coding assistant."
    )
    
    if result:
        print(f"✅ Local generation works!")
        print(f"Model: {result['model']}")
        print(f"Cost saved: ${result['cost_saved']:.6f}")
        print(f"Response: {result['response'][:100]}...")
    else:
        print("❌ Local generation failed")
    
    # Print stats
    stats = llm.get_optimization_stats()
    print(f"\n📊 Optimization Stats:")
    print(f"Available models: {stats['available_models']}")
    print(f"Total cost saved: ${stats['total_cost_saved']:.4f}")
    print(f"Local calls made: {stats['local_calls']}")