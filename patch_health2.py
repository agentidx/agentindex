f = open('/Users/anstudio/agentindex/agentindex/api/discovery.py', 'r')
content = f.read()
f.close()

old = """        session.close()
        
        return {
            "status": "ok", 
            "timestamp": datetime.utcnow().isoformat(),
            "agents": total_agents,
            "active_agents": active_agents
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error", 
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }"""

new = """        session.close()
        
        result = {
            "status": "ok", 
            "timestamp": datetime.utcnow().isoformat(),
            "agents": total_agents,
            "active_agents": active_agents
        }
        _health_cache["data"] = result
        _health_cache["ts"] = _time.time()
        return result
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error", 
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }"""

content = content.replace(old, new)
f = open('/Users/anstudio/agentindex/agentindex/api/discovery.py', 'w')
f.write(content)
f.close()
print("Health cache OK")
