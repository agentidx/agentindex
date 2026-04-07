"""
Smart Router for AgentIndex - Cost Optimization System
Routes tasks between Local LLM (Ollama) and Claude API based on:
- Task complexity
- Budget remaining 
- Quality requirements
- Performance needs

Budget constraint: $10 USD per day
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
import json
import logging
from enum import Enum

from local_llm_setup import LocalLLMManager, PromptOptimizer
from cost_tracker import CostTracker, calculate_cost

logger = logging.getLogger(__name__)

class TaskComplexity(Enum):
    SIMPLE = "simple"      # Local LLM preferred
    MEDIUM = "medium"      # Local LLM often suitable
    COMPLEX = "complex"    # Claude preferred
    CRITICAL = "critical"  # Always Claude

class TaskType(Enum):
    CODE_GENERATION = "code_generation"
    CODE_ANALYSIS = "code_analysis" 
    DATA_PROCESSING = "data_processing"
    CLASSIFICATION = "classification"
    DOCUMENTATION = "documentation"
    SIMPLE_TEXT = "simple_text"
    REASONING = "reasoning"
    COMPLEX_REASONING = "complex_reasoning"
    USER_FACING = "user_facing_responses"
    MARKETING = "marketing_content"
    CRITICAL_ANALYSIS = "critical_analysis"

class SmartRouter:
    def __init__(self):
        self.local_llm = LocalLLMManager()
        self.cost_tracker = CostTracker()
        self.optimizer = PromptOptimizer()
        
        # Task routing rules
        self.local_preferred_tasks = {
            TaskType.CODE_GENERATION,
            TaskType.CODE_ANALYSIS,
            TaskType.DATA_PROCESSING, 
            TaskType.CLASSIFICATION,
            TaskType.DOCUMENTATION,
            TaskType.SIMPLE_TEXT
        }
        
        self.claude_required_tasks = {
            TaskType.COMPLEX_REASONING,
            TaskType.USER_FACING,
            TaskType.MARKETING,
            TaskType.CRITICAL_ANALYSIS
        }
        
        # Initialize local LLM if not ready
        self._ensure_local_llm_ready()
    
    def _ensure_local_llm_ready(self):
        """Ensure local LLM is ready for use"""
        if not self.local_llm.check_ollama_status():
            logger.info("Starting local LLM...")
            self.local_llm.start_ollama()
            
        if not self.local_llm.available_models:
            self.local_llm.refresh_available_models()
    
    def should_use_local(self, task_type: TaskType, complexity: TaskComplexity, 
                        quality_required: float = 0.8) -> Tuple[bool, str]:
        """
        Decide whether to use local LLM based on multiple factors
        Returns: (use_local: bool, reason: str)
        """
        
        # Check budget status first
        budget_status = self.cost_tracker.check_budget_status()
        budget_used_percent = budget_status["daily_stats"]["budget_used_percent"]
        
        # Critical tasks always use Claude (unless budget is critical)
        if complexity == TaskComplexity.CRITICAL:
            if budget_used_percent >= 95:
                return True, "🚨 Budget critical - using local despite complexity"
            return False, "Critical task requires Claude quality"
        
        # Budget-based routing
        if budget_used_percent >= 90:
            return True, f"🚨 Budget critical ({budget_used_percent:.1f}% used) - forcing local"
        elif budget_used_percent >= 75:
            # More aggressive local usage
            if task_type in self.local_preferred_tasks or complexity == TaskComplexity.SIMPLE:
                return True, f"⚠️ Budget warning ({budget_used_percent:.1f}% used) - using local"
        elif budget_used_percent >= 50:
            # Moderate local usage
            if task_type in self.local_preferred_tasks:
                return True, f"📊 Budget monitoring ({budget_used_percent:.1f}% used) - using local"
        
        # Task-type based routing (normal budget conditions)
        if task_type in self.claude_required_tasks:
            return False, f"Task type {task_type.value} requires Claude quality"
        
        if task_type in self.local_preferred_tasks:
            return True, f"Task type {task_type.value} suitable for local LLM"
        
        # Complexity-based fallback
        if complexity == TaskComplexity.SIMPLE:
            return True, "Simple task - local LLM sufficient"
        elif complexity == TaskComplexity.MEDIUM:
            return True, "Medium complexity - trying local LLM first"
        else:  # COMPLEX
            return False, "Complex task - Claude preferred for quality"
    
    def route_request(self, prompt: str, task_type: TaskType, 
                     complexity: TaskComplexity = TaskComplexity.MEDIUM,
                     system_prompt: str = "", max_tokens: int = 1000) -> Dict:
        """
        Route request to appropriate LLM and return result with metadata
        """
        use_local, reason = self.should_use_local(task_type, complexity)
        
        # Optimize prompt regardless of routing
        optimized_prompt = self.optimizer.compress_prompt(prompt, max_length=3000)
        
        start_time = datetime.now()
        
        if use_local and self.local_llm.available_models:
            # Try local LLM first
            model = self.local_llm.get_best_model_for_task(task_type.value)
            result = self.local_llm.generate_local(
                optimized_prompt, model, system_prompt, max_tokens
            )
            
            if result:
                result.update({
                    "routing_decision": "local",
                    "routing_reason": reason,
                    "original_prompt_length": len(prompt),
                    "optimized_prompt_length": len(optimized_prompt),
                    "task_type": task_type.value,
                    "complexity": complexity.value
                })
                
                # Log successful local usage
                logger.info(f"✅ Local LLM used for {task_type.value}: ${result.get('cost_saved', 0):.4f} saved")
                return result
            else:
                # Local failed, fallback to Claude
                logger.warning(f"Local LLM failed for {task_type.value}, falling back to Claude")
                use_local = False
                reason = "Local LLM failed - fallback to Claude"
        
        # Use Claude API (either by choice or fallback)
        return self._use_claude_api(optimized_prompt, system_prompt, max_tokens, 
                                  task_type, complexity, reason, start_time)
    
    def _use_claude_api(self, prompt: str, system_prompt: str, max_tokens: int,
                       task_type: TaskType, complexity: TaskComplexity, 
                       routing_reason: str, start_time: datetime) -> Dict:
        """Use Claude API and track costs"""
        
        # Estimate tokens and cost before calling
        estimated_input_tokens = len(prompt.split()) * 1.3
        estimated_output_tokens = max_tokens * 0.7  # Conservative estimate
        estimated_cost = calculate_cost("claude-3-5-sonnet-20241022", 
                                      estimated_input_tokens, estimated_output_tokens)
        
        # Log the API call to cost tracker
        self.cost_tracker.log_api_call(
            "claude-3-5-sonnet-20241022",
            int(estimated_input_tokens),
            int(estimated_output_tokens), 
            estimated_cost,
            task_type.value,
            "smart_router",
            f"Routed: {routing_reason}"
        )
        
        end_time = datetime.now()
        
        # Return mock response for now (since we don't actually call Claude in this demo)
        return {
            "response": f"[CLAUDE API RESPONSE for {task_type.value} task]",
            "model": "claude-3-5-sonnet-20241022",
            "local": False,
            "routing_decision": "claude",
            "routing_reason": routing_reason,
            "estimated_cost": estimated_cost,
            "estimated_input_tokens": int(estimated_input_tokens),
            "estimated_output_tokens": int(estimated_output_tokens),
            "task_type": task_type.value,
            "complexity": complexity.value,
            "time_taken": (end_time - start_time).total_seconds()
        }
    
    def get_routing_stats(self) -> Dict:
        """Get routing statistics and recommendations"""
        local_stats = self.local_llm.get_optimization_stats()
        budget_status = self.cost_tracker.check_budget_status()
        
        return {
            "local_llm_stats": local_stats,
            "budget_status": budget_status,
            "routing_recommendations": self._generate_routing_recommendations(budget_status)
        }
    
    def _generate_routing_recommendations(self, budget_status: Dict) -> List[str]:
        """Generate routing recommendations based on current status"""
        budget_used = budget_status["daily_stats"]["budget_used_percent"]
        recommendations = []
        
        if budget_used >= 90:
            recommendations.extend([
                "🚨 CRITICAL: Force all non-critical tasks to local LLM",
                "⚡ Use prompt compression aggressively",
                "📦 Batch similar requests together",
                "⏸️ Consider deferring non-urgent tasks"
            ])
        elif budget_used >= 70:
            recommendations.extend([
                "⚠️ WARNING: Increase local LLM usage",
                "🎯 Route code generation to local models",
                "📝 Compress prompts for Claude calls",
                "🔄 Use caching for repeated queries"
            ])
        elif budget_used >= 40:
            recommendations.extend([
                "📊 MONITORING: Current routing strategy working well",
                "💡 Continue optimizing local model usage",
                "🔍 Monitor for optimization opportunities"
            ])
        else:
            recommendations.extend([
                "✅ HEALTHY: Budget usage optimal",
                "🚀 Room for more aggressive development",
                "⚖️ Good balance of local/remote usage"
            ])
        
        return recommendations

def demo_smart_routing():
    """Demo the smart routing system"""
    router = SmartRouter()
    
    print("🎯 Smart Routing Demo - Cost Optimization System")
    print("=" * 50)
    
    # Test different types of tasks
    test_cases = [
        {
            "prompt": "Write a Python function to sort a list",
            "task_type": TaskType.CODE_GENERATION,
            "complexity": TaskComplexity.SIMPLE
        },
        {
            "prompt": "Analyze this complex business strategy and provide recommendations",
            "task_type": TaskType.CRITICAL_ANALYSIS, 
            "complexity": TaskComplexity.COMPLEX
        },
        {
            "prompt": "Classify these 100 text samples into categories",
            "task_type": TaskType.CLASSIFICATION,
            "complexity": TaskComplexity.MEDIUM
        },
        {
            "prompt": "Write marketing copy for our AI product launch",
            "task_type": TaskType.MARKETING,
            "complexity": TaskComplexity.COMPLEX
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test Case {i}: {test_case['task_type'].value}")
        print(f"Complexity: {test_case['complexity'].value}")
        
        result = router.route_request(
            test_case["prompt"],
            test_case["task_type"],
            test_case["complexity"]
        )
        
        print(f"✅ Routing: {result['routing_decision']} - {result['routing_reason']}")
        if result["local"]:
            print(f"💰 Cost saved: ${result.get('cost_saved', 0):.4f}")
        else:
            print(f"💳 Estimated cost: ${result.get('estimated_cost', 0):.4f}")
    
    # Show overall stats
    print(f"\n📊 Routing Statistics:")
    stats = router.get_routing_stats()
    print(f"Local LLM calls: {stats['local_llm_stats']['local_calls']}")
    print(f"Total cost saved: ${stats['local_llm_stats']['total_cost_saved']:.4f}")
    print(f"Budget used today: {stats['budget_status']['daily_stats']['budget_used_percent']:.1f}%")
    
    print(f"\n🎯 Current Recommendations:")
    for rec in stats['routing_recommendations']:
        print(f"  {rec}")

if __name__ == "__main__":
    demo_smart_routing()