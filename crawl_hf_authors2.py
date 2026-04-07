#!/usr/bin/env python3
import requests, time, logging, uuid, psycopg2, psycopg2.extras, json, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-auth2] %(message)s",
    handlers=[logging.FileHandler(f'hf_authors2_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("hf_auth2")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')
HEADERS = {'User-Agent': 'AgentIndex/1.0', 'Accept': 'application/json'}
def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT author, COUNT(*) as cnt FROM agents WHERE source LIKE 'huggingface%%' AND author IS NOT NULL AND author != 'unknown' AND author != '' GROUP BY author ORDER BY cnt DESC")
    authors = [(r[0], r[1]) for r in cur.fetchall()]
    logger.info(f"Found {len(authors)} authors")
    total_new = 0
    rl = 0
    for i, (author, ec) in enumerate(authors, 1):
        try:
            resp = requests.get('https://huggingface.co/api/models', params={'author': author, 'limit': 100}, headers=HEADERS, timeout=5)
            if resp.status_code == 429:
                rl += 1
                if rl > 5:
                    logger.warning(f"Rate limited x{rl}. Sleeping 120s")
                    time.sleep(120)
                    rl = 0
                else:
                    time.sleep(10)
                continue
            if resp.status_code != 200:
                time.sleep(0.5)
                continue
            models = resp.json()
            if not models:
                time.sleep(0.3)
                continue
            values = []
            for m in models:
                mid = m.get('id', '')
                if not mid: continue
                a, n = mid.split('/', 1) if '/' in mid else ('unknown', mid)
                values.append((str(uuid.uuid4()), 'huggingface_author2', f"https://huggingface.co/{mid}", mid, n[:500], (m.get('description') or mid)[:2000], a[:255], m.get('likes', 0), m.get('downloads', 0), (m.get('tags') or [])[:10], ['huggingface_api'], json.dumps(m), datetime.now(), datetime.now(), True, 'indexed'))
            ins = 0
            if values:
                try:
                    psycopg2.extras.execute_values(cur, """INSERT INTO agents (id, source, source_url, source_id, name, description, author, stars, downloads, tags, protocols, raw_metadata, first_indexed, last_crawled, is_active, crawl_status) VALUES %s ON CONFLICT (source_url) DO NOTHING""", values, page_size=100)
                    conn.commit()
                    ins = cur.rowcount
                    total_new += ins
                except Exception as e:
                    logger.error(f"Insert error: {e}")
                    conn.rollback()
            if i % 100 == 0 or ins > 20:
                cur.execute("SELECT COUNT(*) FROM agents")
                db = cur.fetchone()[0]
                logger.info(f"[{i}/{len(authors)}] '{author}' (had {ec}): +{ins} | Session: {total_new:,} | DB: {db:,}")
            time.sleep(0.5)
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"Error '{author}': {e}")
            time.sleep(1)
    cur.execute("SELECT COUNT(*) FROM agents")
    db = cur.fetchone()[0]
    logger.info(f"COMPLETE: {total_new:,} new from {len(authors)} authors | DB: {db:,}")
    conn.close()
if __name__ == '__main__':
    main()
