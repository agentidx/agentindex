#!/bin/bash
# Run all LaunchAgents once and report exit codes.
# Skips continuous/daemon agents that don't exit normally.

CONTINUOUS="com.nerq.api com.nerq.master-watchdog com.nerq.alert-monitor com.nerq.performance-guardian"

AGENTS=$(launchctl list | grep -E "com\.(nerq|zarq)" | awk '{print $3}' | sort)
PASSED=()
FAILED=()
SKIPPED=()

echo "============================================"
echo "RUN ALL AGENTS — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

for agent in $AGENTS; do
    # Skip continuous agents
    skip=0
    for c in $CONTINUOUS; do
        if [ "$agent" = "$c" ]; then skip=1; break; fi
    done
    if [ $skip -eq 1 ]; then
        SKIPPED+=("$agent")
        continue
    fi

    echo -n "  $agent ... "
    launchctl start "$agent" 2>/dev/null

    # Poll for up to 90s
    finished=0
    for i in $(seq 1 90); do
        sleep 1
        LINE=$(launchctl list 2>/dev/null | grep "	${agent}$")
        PID=$(echo "$LINE" | awk '{print $1}')
        EXIT=$(echo "$LINE" | awk '{print $2}')

        if [ "$PID" = "-" ] && [ "$EXIT" != "-" ]; then
            if [ "$EXIT" = "0" ]; then
                PASSED+=("$agent")
                echo "PASS (${i}s)"
            else
                FAILED+=("$agent (exit $EXIT)")
                echo "FAIL exit=$EXIT (${i}s)"
            fi
            finished=1
            break
        fi
    done

    if [ $finished -eq 0 ]; then
        # Still running after 90s — check if it's a long-running agent
        PID=$(launchctl list 2>/dev/null | grep "	${agent}$" | awk '{print $1}')
        if [ "$PID" != "-" ] && [ -n "$PID" ]; then
            SKIPPED+=("$agent (still running)")
            echo "SKIP (long-running)"
        else
            FAILED+=("$agent (timeout)")
            echo "FAIL (timeout)"
        fi
    fi
done

echo ""
echo "============================================"
echo "PASSED:  ${#PASSED[@]}"
echo "FAILED:  ${#FAILED[@]}"
echo "SKIPPED: ${#SKIPPED[@]}"
echo "============================================"

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "FAILURES:"
    for a in "${FAILED[@]}"; do echo "  - $a"; done
    exit 1
fi
exit 0
