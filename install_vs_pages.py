#!/usr/bin/env python3
"""Install VS pages into the Nerq API."""
import os
import shutil

BASE = os.path.expanduser("~/agentindex")
SRC = os.path.join(BASE, "vs_pages.py")
DST = os.path.join(BASE, "agentindex", "vs_pages.py")
DISC = os.path.join(BASE, "agentindex", "api", "discovery.py")
SEO = os.path.join(BASE, "agentindex", "seo_pages.py")

def install():
    # 1. Copy module
    if os.path.exists(SRC):
        shutil.copy2(SRC, DST)
        print(f"1. Copied vs_pages.py to {DST}")
    else:
        print("ERROR: vs_pages.py not found in ~/agentindex/")
        return

    # 2. Mount in discovery.py
    with open(DISC, 'r') as f:
        content = f.read()

    if 'mount_vs_pages' in content:
        print("2. vs_pages already mounted")
    else:
        old = "from agentindex.comparison_pages import mount_comparison_pages\nmount_comparison_pages(app)"
        new = (old + "\n\n"
               "from agentindex.vs_pages import mount_vs_pages\n"
               "mount_vs_pages(app)")
        if old in content:
            content = content.replace(old, new)
            with open(DISC, 'w') as f:
                f.write(content)
            print("2. Added mount_vs_pages to discovery.py")
        else:
            print("2. WARNING: Could not find comparison_pages mount. Add manually.")

    # 3. Add sitemap-vs to sitemap-index
    with open(SEO, 'r') as f:
        seo_content = f.read()

    if 'sitemap-vs.xml' in seo_content:
        print("3. sitemap-vs already in sitemap-index")
    else:
        old_sm = "xml += f'  <sitemap><loc>{SITE_URL}/sitemap-comparisons.xml</loc><lastmod>{now}</lastmod></sitemap>\\n'"
        new_sm = (old_sm + "\n"
                  "            xml += f'  <sitemap><loc>{SITE_URL}/sitemap-vs.xml</loc><lastmod>{now}</lastmod></sitemap>\\n'")
        if old_sm in seo_content:
            seo_content = seo_content.replace(old_sm, new_sm)
            with open(SEO, 'w') as f:
                f.write(seo_content)
            print("3. Added sitemap-vs.xml to sitemap-index")
        else:
            print("3. WARNING: Could not add sitemap-vs to sitemap-index")

    print("\nDone! Restart API:")
    print("  kill $(ps aux | grep discovery | grep -v grep | awk '{print $2}') 2>/dev/null")
    print("  sleep 2 && nohup python -m agentindex.api.discovery > logs/api.log 2>&1 &")

if __name__ == "__main__":
    install()
