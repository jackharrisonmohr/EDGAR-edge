import feedparser, time, json, datetime as dt
from pathlib import Path

# Use the local file for simulation
RSS_FILE = "../../tests/test_data/feed_snapshot.xml"
seen = set()

# Read from the local file instead of the live feed
with open(RSS_FILE, 'r') as f:
    feed = feedparser.parse(f.read())

for entry in feed.entries:
    if entry.id in seen:
        continue
    seen.add(entry.id)
    filing = {
        "accession_no": entry.id.split("accession-number=")[-1],
        "title": entry.title,
        "filed_at": entry.updated,
        "link": entry.link,
    }
    Path("../../tmp").mkdir(exist_ok=True)
    Path("../../tmp").joinpath(f"{filing['accession_no']}.json").write_text(json.dumps(filing))

print(f"Processed {len(feed.entries)} entries from the snapshot.")
