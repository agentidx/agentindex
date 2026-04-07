import re

f = open('/Users/anstudio/agentindex/agentindex/api/discovery.py', 'r')
content = f.read()
f.close()

# Add cache imports and variable after existing imports
old = 'from datetime import datetime'
new = '''from datetime import datetime
import time as _time

# Stats cache
_stats_cache = {"data": None, "ts": 0}
_STATS_TTL = 300  # 5 minutes'''
content = content.replace(old, new, 1)

# Replace stats function with cached version
old_func = '''def stats():
    """Public statistics about the index."""
    session = get_session()

    total = session.execute(
        select(func.count(Agent.id))
    ).scalar() or 0'''

new_func = '''def stats():
    """Public statistics about the index (cached 5 min)."""
    if _stats_cache["data"] and (_time.time() - _stats_cache["ts"]) < _STATS_TTL:
        return _stats_cache["data"]
    
    session = get_session()

    total = session.execute(
        select(func.count(Agent.id))
    ).scalar() or 0'''
content = content.replace(old_func, new_func)

# Add cache store before return
old_return = '''    return StatsResponse(
        total_agents=total,
        active_agents=active,
        categories=categories,
        sources=sources,
        protocols=protocol_counts,
        last_crawl=datetime.utcnow().isoformat(),
    )'''

new_return = '''    result = StatsResponse(
        total_agents=total,
        active_agents=active,
        categories=categories,
        sources=sources,
        protocols=protocol_counts,
        last_crawl=datetime.utcnow().isoformat(),
    )
    _stats_cache["data"] = result
    _stats_cache["ts"] = _time.time()
    return result'''
content = content.replace(old_return, new_return)

f = open('/Users/anstudio/agentindex/agentindex/api/discovery.py', 'w')
f.write(content)
f.close()
print("Patched OK")
