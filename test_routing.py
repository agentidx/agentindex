#!/usr/bin/env python3
"""Test the smart routing system"""

from smart_router import SmartRouter, TaskType, TaskComplexity

router = SmartRouter()

# Test routing decisions (testing should_use_local method)
test_tasks = [
    ('Code generation task', TaskType.CODE_GENERATION, TaskComplexity.SIMPLE),
    ('Complex data analysis', TaskType.COMPLEX_REASONING, TaskComplexity.COMPLEX),
    ('Basic documentation', TaskType.DOCUMENTATION, TaskComplexity.SIMPLE),
    ('Strategic planning', TaskType.CRITICAL_ANALYSIS, TaskComplexity.CRITICAL),
    ('Simple classification', TaskType.CLASSIFICATION, TaskComplexity.SIMPLE),
    ('User-facing response', TaskType.USER_FACING, TaskComplexity.MEDIUM)
]

print('=== SMART ROUTING TEST ===')
for task_desc, task_type, complexity in test_tasks:
    use_local, reason = router.should_use_local(task_type, complexity)
    route = "LOCAL LLM" if use_local else "CLAUDE API"
    print(f'Task: "{task_desc}"')
    print(f'Type: {task_type.value}, Complexity: {complexity.value}')
    print(f'Route: {route}')
    print(f'Reason: {reason}')
    print()

# Test budget-based routing
print('=== BUDGET STATUS IMPACT ===')
budget_status = router.cost_tracker.check_budget_status()
print(f'Budget status: {budget_status["status"]}')
print(f'Current usage: {budget_status.get("percentage", 0):.1f}%')

# Test local LLM availability
print('\n=== LOCAL LLM STATUS ===')
print(f'Ollama running: {router.local_llm.check_ollama_status()}')
print(f'Available models: {len(router.local_llm.available_models)}')
if router.local_llm.available_models:
    for model in router.local_llm.available_models:
        print(f'- {model}')
else:
    router.local_llm.refresh_available_models()
    print(f'After refresh: {router.local_llm.available_models}')