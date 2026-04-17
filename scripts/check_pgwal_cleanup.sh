#!/bin/bash
# Verify pgBackRest WAL archiving + cleanup status on Nbg
echo "=== pgBackRest Archive Status ==="
ready=$(ssh root@100.119.193.70 "ls /var/lib/postgresql/16/main/pg_wal/archive_status/*.ready 2>/dev/null | wc -l" 2>&1 | grep -v perl | grep -v warning | tr -d ' ')
echo "Ready files (pending archive): $ready"

echo "=== pg_wal Size ==="
ssh root@100.119.193.70 "du -sh /var/lib/postgresql/16/main/pg_wal/" 2>&1 | grep -v perl | grep -v warning

echo "=== Disk Status ==="
ssh root@100.119.193.70 "df -h / | tail -1" 2>&1 | grep -v perl | grep -v warning

echo "=== Archiver Stats ==="
ssh root@100.119.193.70 "psql -h /var/run/postgresql -U anstudio -d postgres -tAc \"SELECT 'archived=' || archived_count || ' failed=' || failed_count FROM pg_stat_archiver\"" 2>&1 | grep -v perl | grep -v warning

if [ "$ready" = "0" ]; then
    echo ""
    echo "ALL ARCHIVED. Ready for CHECKPOINT + WAL cleanup."
    echo "Run: ssh root@100.119.193.70 \"psql -h /var/run/postgresql -U anstudio -d postgres -c 'CHECKPOINT;'\""
else
    echo ""
    echo "Still archiving. Check again in $(( ready / 60 )) minutes."
fi
