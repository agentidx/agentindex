#!/bin/bash
# Regression Test Suite — Phase 0 Stability Sprint
# Verifies all fixes from Dag 1 + Dag 2 actually work.
# Exit 0 if all pass, 1 if any fail.

PSQL="/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
PASS=0
FAIL=0
FAILURES=""

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "  PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $name"
        FAIL=$((FAIL + 1))
        FAILURES="$FAILURES\n  - $name"
    fi
}

echo "============================================================"
echo "REGRESSION TEST SUITE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""

# T1: No hardcoded DATABASE_URL fallbacks to localhost in agentindex/
echo "T1: No hardcoded DATABASE_URL localhost fallbacks"
t1=$(grep -rn 'os.environ.get("DATABASE_URL", "postgresql://localhost' agentindex/ --include="*.py" | grep -v __pycache__ | grep -v db_config.py | grep -v test_ | wc -l | tr -d ' ')
check "T1: hardcoded localhost fallbacks = $t1" "$([ "$t1" -eq 0 ] && echo 0 || echo 1)"

# T2: No hardcoded socket DSNs with old IPs
echo "T2: No hardcoded old IP DSNs"
t2=$(grep -rn 'host=.100\.90\.152\.88' agentindex/ --include="*.py" | grep -v __pycache__ | grep -v ".bak" | wc -l | tr -d ' ')
check "T2: old IP references = $t2" "$([ "$t2" -eq 0 ] && echo 0 || echo 1)"

# T3: db_config used by 27+ files
echo "T3: db_config adoption"
t3=$(grep -rln "from agentindex.db_config\|import db_config" agentindex --include="*.py" | grep -v __pycache__ | wc -l | tr -d ' ')
check "T3: files using db_config = $t3 (need >=27)" "$([ "$t3" -ge 27 ] && echo 0 || echo 1)"

# T4: stale-scores LEFT JOIN fix
echo "T4: stale-scores LEFT JOIN agents"
grep -q "LEFT JOIN agents" agentindex/stale_score_detector.py 2>/dev/null
check "T4: LEFT JOIN agents present" "$?"

# T5: vitality busy_timeout
echo "T5: vitality SQLite busy_timeout"
grep -q "busy_timeout" agentindex/crypto/vitality_score.py 2>/dev/null
check "T5: busy_timeout in vitality_score.py" "$?"

# T6: pg_stat_statements on all nodes
echo "T6: pg_stat_statements"
t6_mac=$($PSQL -U anstudio -d agentindex -tAc "SELECT COUNT(*) FROM pg_extension WHERE extname='pg_stat_statements'" 2>/dev/null | tr -d ' ')
t6_nbg=$($PSQL -U anstudio -h 100.119.193.70 -d agentindex -tAc "SELECT COUNT(*) FROM pg_extension WHERE extname='pg_stat_statements'" 2>/dev/null | tr -d ' ')
t6_hel=$($PSQL -U anstudio -h 100.79.171.54 -d agentindex -tAc "SELECT COUNT(*) FROM pg_extension WHERE extname='pg_stat_statements'" 2>/dev/null | tr -d ' ')
t6_total=$(( ${t6_mac:-0} + ${t6_nbg:-0} + ${t6_hel:-0} ))
check "T6: pg_stat_statements on 3 nodes (Mac:${t6_mac:-0} Nbg:${t6_nbg:-0} Hel:${t6_hel:-0})" "$([ "$t6_total" -eq 3 ] && echo 0 || echo 1)"

# T7: PgBouncer running
echo "T7: PgBouncer"
t7_running=$(brew services list 2>/dev/null | grep pgbouncer | grep -c started)
t7_port=$(lsof -i :6432 2>/dev/null | grep -c LISTEN)
t7_query=$($PSQL -h 127.0.0.1 -p 6432 -U anstudio -d agentindex_read -tAc "SELECT 1" 2>/dev/null | tr -d ' ')
check "T7: PgBouncer (running:$t7_running port:$t7_port query:${t7_query:-fail})" "$([ "$t7_running" -ge 1 ] && [ "${t7_query:-0}" = "1" ] && echo 0 || echo 1)"

# T8: Alert monitor active
echo "T8: Alert monitor"
t8=$(launchctl list 2>/dev/null | grep -c alert-monitor)
check "T8: alert-monitor registered = $t8" "$([ "$t8" -ge 1 ] && echo 0 || echo 1)"

# T9: 0 read-only errors in last 30 min
echo "T9: Read-only errors (last 30 min)"
cutoff=$(date -v -30M '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '30 minutes ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null)
t9=$(awk -v c="$cutoff" '$1" "$2 >= c' /opt/homebrew/var/log/postgresql@16.log 2>/dev/null | grep -c "cannot execute.*read-only")
check "T9: read-only errors since $cutoff = $t9" "$([ "$t9" -eq 0 ] && echo 0 || echo 1)"

# T10: Replication 0 lag, 2 replicas
echo "T10: Replication"
t10=$($PSQL -U anstudio -h 100.119.193.70 -d agentindex -tAc "SELECT COUNT(*) FROM pg_stat_replication WHERE state = 'streaming' AND pg_wal_lsn_diff(sent_lsn, replay_lsn) < 1000000" 2>/dev/null | tr -d ' \n')
check "T10: streaming replicas <1MB lag = ${t10:-0} (need 2)" "$([ "${t10:-0}" -ge 2 ] && echo 0 || echo 1)"

# T11: API responds < 500ms for 10 requests
echo "T11: API latency"
t11_fail=0
for i in $(seq 1 10); do
    ms=$(curl -s -o /dev/null -w "%{time_total}" http://localhost:8000/v1/health 2>/dev/null)
    ms_int=$(echo "$ms * 1000" | bc 2>/dev/null | cut -d. -f1)
    if [ "${ms_int:-9999}" -gt 500 ]; then
        t11_fail=$((t11_fail + 1))
    fi
done
check "T11: API requests >500ms = $t11_fail/10" "$([ "$t11_fail" -eq 0 ] && echo 0 || echo 1)"

# T12: API functional test
echo "T12: API functional"
t12_home=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
t12_safe=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/safe/nordvpn)
t12_pf=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/v1/preflight?target=express")
check "T12: endpoints (home:$t12_home safe:$t12_safe preflight:$t12_pf)" "$([ "$t12_home" = "200" ] && [ "$t12_safe" = "200" ] && [ "$t12_pf" = "200" ] && echo 0 || echo 1)"

# Summary
echo ""
echo "============================================================"
echo "RESULTS: $PASS PASS, $FAIL FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo -e "FAILURES:$FAILURES"
    echo "============================================================"
    exit 1
else
    echo "ALL TESTS PASSED"
    echo "============================================================"
    exit 0
fi
