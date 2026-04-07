#!/usr/bin/env python3
"""Full HuggingFace Datasets catalog crawl."""
import logging, uuid, psycopg2, psycopg2.extras, json, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
try:
    from huggingface_hub import HfApi
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'huggingface_hub', '--break-system-packages'])
    from huggingface_hub import HfApi

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hf-ds] %(message)s",
    handlers=[logging.FileHandler(f'hf_full_datasets_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("hf_ds")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

def main():
    api = HfApi()
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    total_new = 0
    total_processed = 0
    batch = []
    batch_size = 500
    
    logger.info("Starting FULL HuggingFace Datasets catalog crawl")
    
    for ds in api.list_datasets(sort="_id", direction=1):
        ds_id = ds.id if hasattr(ds, 'id') else str(ds)
        if not ds_id:
            continue
        author, name = ds_id.split('/', 1) if '/' in ds_id else ('unknown', ds_id)
        tags = list(ds.tags) if hasattr(ds, 'tags') and ds.tags else []
        batch.append((
            str(uuid.uuid4()), 'huggingface_dataset_full', f"https://huggingface.co/datasets/{ds_id}",
            ds_id, name[:500], ''[:2000], author[:255],
            getattr(ds, 'likes', 0) or 0, getattr(ds, 'downloads', 0) or 0,
            tags[:10], ['huggingface_hub'], json.dumps({'id': ds_id, 'tags': tags[:10]}),
            datetime.now(), datetime.now(), True, 'indexed'
        ))
        total_processed += 1
        
        if len(batch) >= batch_size:
            try:
                psycopg2.extras.execute_values(cur, """INSERT INTO agents (
                    id, source, source_url, source_id, name, description, author,
                    stars, downloads, tags, protocols, raw_metadata,
                    first_indexed, last_crawled, is_active, crawl_status
                ) VALUES %s ON CONFLICT (source_url) DO NOTHING""", batch, page_size=500)
                conn.commit()
                inserted = cur.rowcount
                total_new += inserted
            except Exception as e:
                logger.error(f"Insert error: {e}")
                conn.rollback()
                inserted = 0
            batch = []
            if total_processed % 5000 == 0:
                cur.execute("SELECT COUNT(*) FROM agents")
                db = cur.fetchone()[0]
                logger.info(f"Processed: {total_processed:,} | New: {total_new:,} | DB: {db:,}")
    
    if batch:
        try:
            psycopg2.extras.execute_values(cur, """INSERT INTO agents (
                id, source, source_url, source_id, name, description, author,
                stars, downloads, tags, protocols, raw_metadata,
                first_indexed, last_crawled, is_active, crawl_status
            ) VALUES %s ON CONFLICT (source_url) DO NOTHING""", batch, page_size=500)
            conn.commit()
            total_new += cur.rowcount
        except Exception as e:
            logger.error(f"Final insert error: {e}")
            conn.rollback()
    
    cur.execute("SELECT COUNT(*) FROM agents")
    db = cur.fetchone()[0]
    logger.info(f"DATASETS COMPLETE: {total_new:,} new from {total_processed:,} processed | DB: {db:,}")
    conn.close()

if __name__ == '__main__':
    main()
