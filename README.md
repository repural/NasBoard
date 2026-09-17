# NasBoard

Nasdaq market-regime dashboard. The site is designed for GitHub Pages and refreshes its generated `data/dashboard.json` snapshot via GitHub Actions.

## Refresh schedule
The workflow checks at 13:30, 14:30 and 15:30 UTC on weekdays and only runs the data refresh when the corresponding New York time is 09:30 or 10:30. This handles EST/EDT without changing cron expressions.

## Data policy
Each metric carries a source timestamp/freshness label. Official/free sources are preferred; unavailable metrics remain explicitly marked stale/limited rather than being invented.
