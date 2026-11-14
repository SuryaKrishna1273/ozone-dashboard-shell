# weekly-brand-reports

Code for the Monday Meta Ads weekly brand reports (Epigroww). Run by a Claude scheduled task.

- `prep.py` – dates, duplicate-check query, creative ids, thumbnails, build config, email fields
- `grab.py` – saves each Meta Ads answer to a file so no number is retyped
- `build_report.py` – checks totals (campaign = ad = account) and builds the one-page PDF

Recipients live in the scheduled task, not in this repo.
