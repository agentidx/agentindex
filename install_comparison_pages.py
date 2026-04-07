#!/usr/bin/env python3
"""
Install comparison pages into the Nerq API.
1. Copies comparison_pages.py to agentindex/
2. Adds import + mount_comparison_pages(app) to discovery.py
3. Updates sitemap-index to include comparison sitemap

Run: cd ~/agentindex && source venv/bin/activate && python install_comparison_pages.py
Then restart API.
"""
import os
import shutil

BASE = os.path.expanduser("~/agentindex")
SRC = os.path.join(BASE, "comparison_pages.py")
DST = os.path.join(BASE, "agentindex", "comparison_pages.py")
DISC = os.path.join(BASE, "agentindex", "api", "discovery.py")


def install():
    # Step 1: Copy to agentindex/ package
    if os.path.exists(SRC):
        shutil.copy2(SRC, DST)
        print(f"1. Copied comparison_pages.py to {DST}")
    elif os.path.exists(DST):
        print(f"1. comparison_pages.py already in {DST}")
    else:
        print("ERROR: comparison_pages.py not found!")
        return

    # Step 2: Add import and mount to discovery.py
    with open(DISC, 'r') as f:
        content = f.read()

    # Check if already installed
    if 'mount_comparison_pages' in content:
        print("2. comparison_pages already mounted in discovery.py")
    else:
        # Find where seo_pages is mounted and add after it
        old = "from agentindex.seo_pages import mount_seo_pages\nmount_seo_pages(app)"
        new = (
            "from agentindex.seo_pages import mount_seo_pages\n"
            "mount_seo_pages(app)\n\n"
            "from agentindex.comparison_pages import mount_comparison_pages\n"
            "mount_comparison_pages(app)"
        )
        
        if old in content:
            content = content.replace(old, new)
            with open(DISC, 'w') as f:
                f.write(content)
            print("2. Added mount_comparison_pages to discovery.py")
        else:
            print("2. WARNING: Could not find seo_pages mount pattern.")
            print("   Add manually to discovery.py:")
            print("     from agentindex.comparison_pages import mount_comparison_pages")
            print("     mount_comparison_pages(app)")

    print("\nDone! Restart API to activate:")
    print("  kill $(ps aux | grep discovery | grep -v grep | awk '{print $2}') 2>/dev/null")
    print("  sleep 2 && cd ~/agentindex && nohup python -m agentindex.api.discovery > logs/api.log 2>&1 &")


if __name__ == "__main__":
    install()
