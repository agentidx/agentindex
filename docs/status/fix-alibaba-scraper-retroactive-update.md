# Analytics: Retroactive Fix for Alibaba Scraper Classification

Date: 2026-04-12 (Sunday evening 19:56 CEST)
Status: Applied — 186,245 historical rows reclassified

## What was done

Following the live fix committed in 28b91dd (classifying Alibaba
Cloud Singapore IPs as 'Datacenter Scraper' bots going forward),
this retroactive fix applies the same classification to all
historical data from 2026-03-13 onwards.

## Rows updated

SQL: UPDATE requests SET is_bot=1, bot_name='Datacenter Scraper'
     WHERE is_bot=0 AND ip LIKE '43.172.%' OR LIKE '43.173.%'
                       OR LIKE '47.79.%' OR LIKE '47.82.%'

Total: 186,245 rows reclassified.

## Aggregation refresh

Scripts/refresh_analytics_aggregation.py temporarily changed from
DAYS_TO_REFRESH=3 to DAYS_TO_REFRESH=35, then reverted.

Refreshed 23,628 rows in requests_daily across 30 days.

## Impact on Singapore metrics

Before:
- 2026-04-11: 50,219 'human' visits
- 2026-04-12: 41,797 'human' visits

After:
- 2026-04-11: 190 human visits (actual)
- 2026-04-12: 151 human visits (actual)

250x reduction, reflecting actual human traffic from Singapore.
All historical dashboards now show correct data.

## Backup

Full analytics.db backup: analytics.db.bak-pre-historical-update-1952
Size: 9.7 GB. Retain for one week then delete.

## Cache refresh

- /tmp/nerq_analytics_dashboard.json regenerated
- ~/agentindex/logs/flywheel_cache/*.json cleared
- Both /admin/analytics-dashboard and /flywheel now serve fresh data
