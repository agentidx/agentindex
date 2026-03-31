"""
Safety & Security Guide Pages + Breach Integration
=====================================================
30 curated guide pages + breach-enhanced entity pages.

Usage:
    from agentindex.guide_pages import mount_guide_pages
    mount_guide_pages(app)
"""

import html as html_mod
import json
import logging
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.guides")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MY = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600

def _c(k):
    e = _cache.get(k)
    return e[1] if e and (time.time() - e[0]) < CACHE_TTL else None

def _sc(k, v):
    _cache[k] = (time.time(), v)
    return v

def _esc(t):
    return html_mod.escape(str(t)) if t else ""

def _head(title, desc, canonical, extra=""):
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}"><meta property="og:description" content="{_esc(desc)}">
<meta name="citation_title" content="{_esc(title)}"><meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}"><meta name="robots" content="max-snippet:-1">
{extra}{NERQ_CSS}
<style>ol li,ul li{{margin-bottom:8px}}h2{{margin-top:28px}}table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}</style>
</head><body>{NERQ_NAV}<main class="container" style="max-width:800px;margin:0 auto;padding:24px">"""

def _foot():
    return f"""<p style="font-size:12px;color:#6b7280;margin-top:24px">Updated {MY}. Source: Nerq independent analysis.</p>
</main>{NERQ_FOOTER}</body></html>"""


# All guide definitions: slug → (title, description, content_html)
GUIDES = {
    "how-to-spot-fake-website": {
        "title": f"How to Spot a Fake Website — {YEAR} Guide",
        "desc": f"Learn to identify fake and scam websites. 10 red flags to check before entering personal info or making a purchase. Updated {MY}.",
        "content": f"""
<h1>How to Spot a Fake Website — {YEAR} Guide</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Fake websites steal billions annually. Here are 10 data-backed red flags to check before trusting any website. Use Nerq's website trust checker for instant analysis.</p>

<h2>10 Red Flags of a Fake Website</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Domain age under 6 months</strong> — 87% of scam sites are less than 6 months old. Check domain registration date.</li>
<li><strong>No HTTPS / invalid SSL</strong> — Legitimate sites have valid SSL certificates. Look for the padlock icon.</li>
<li><strong>Prices too good to be true</strong> — 50-90% off luxury brands is almost always a scam.</li>
<li><strong>No contact information</strong> — No phone number, physical address, or real email (only a contact form).</li>
<li><strong>Poor grammar and spelling</strong> — Especially in the domain name itself (amaz0n.com, g00gle.com).</li>
<li><strong>Payment only via wire transfer or crypto</strong> — Legitimate stores accept credit cards with buyer protection.</li>
<li><strong>No social media presence</strong> — Or fake social accounts with no real engagement.</li>
<li><strong>Copied content</strong> — Text and images stolen from legitimate websites.</li>
<li><strong>Excessive pop-ups and redirects</strong> — Legitimate sites don't bombard you with pop-ups.</li>
<li><strong>No return/refund policy</strong> — Or a policy that's clearly copied from another site.</li>
</ol>

<h2>How to Check Any Website</h2>
<p style="font-size:14px;color:#374151">Use Nerq to check any website's trust score: <code>nerq.ai/is-[website]-safe</code> or search above.</p>

<h2>What to Do If You've Been Scammed</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Contact your bank immediately to dispute the charge</li>
<li>Report the site to your country's consumer protection agency</li>
<li>Report to the FTC (US), Action Fraud (UK), or equivalent</li>
<li>Change passwords if you created an account on the scam site</li>
<li>Monitor your credit report for unauthorized activity</li>
</ol>
"""},

    "what-to-do-if-hacked": {
        "title": f"What to Do If You've Been Hacked — {YEAR} Guide",
        "desc": f"Step-by-step guide if your account was hacked. Secure your accounts, check for damage, prevent future attacks. Updated {MY}.",
        "content": f"""
<h1>What to Do If You've Been Hacked — Step by Step {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">If you suspect your account has been compromised, act fast. Here's the complete response checklist, prioritized by urgency.</p>

<h2>Immediate Actions (First 30 Minutes)</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Change your password immediately</strong> — Start with the compromised account, then any accounts using the same password</li>
<li><strong>Enable two-factor authentication (2FA)</strong> — Use an authenticator app, not SMS</li>
<li><strong>Check for unauthorized transactions</strong> — Review bank statements and payment accounts</li>
<li><strong>Log out of all sessions</strong> — Most services have a "log out everywhere" option in security settings</li>
<li><strong>Revoke app access</strong> — Check connected apps and remove any you don't recognize</li>
</ol>

<h2>Next 24 Hours</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Check haveibeenpwned.com</strong> — See if your email appears in known data breaches</li>
<li><strong>Run a malware scan</strong> — Scan all devices for keyloggers and malware</li>
<li><strong>Update all passwords</strong> — Use a password manager to generate unique passwords</li>
<li><strong>Notify your bank</strong> — If financial data was exposed, request fraud monitoring</li>
<li><strong>Check email forwarding rules</strong> — Hackers often set up forwarding to maintain access</li>
</ol>

<h2>Prevention</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Use a password manager (Bitwarden, 1Password)</li>
<li>Enable 2FA on every account that supports it</li>
<li>Never reuse passwords</li>
<li>Be skeptical of links in emails and messages</li>
<li>Keep software updated</li>
<li>Use Nerq to check software trust before installing: <code>nerq.ai/is-[tool]-safe</code></li>
</ul>
"""},

    "internet-safety-for-kids": {
        "title": f"Internet Safety for Kids — Parent Guide {YEAR}",
        "desc": f"Complete parent guide to keeping kids safe online. Age-appropriate tips, app reviews, parental controls. Updated {MY}.",
        "content": f"""
<h1>Internet Safety for Kids — Parent Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Children are online earlier than ever. This guide helps parents protect their kids at every age. Check any app's safety at nerq.ai/is-[app]-safe-for-kids.</p>

<h2>Ages 5-8: Supervised Use Only</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Always supervise screen time</li>
<li>Use YouTube Kids instead of regular YouTube</li>
<li>Disable in-app purchases on all devices</li>
<li>Use parental controls on tablets and phones</li>
<li>Stick to age-rated apps (check ratings at nerq.ai)</li>
</ul>

<h2>Ages 9-12: Guided Independence</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Teach about not sharing personal information</li>
<li>Review friend lists and chat features together</li>
<li>Set up screen time limits</li>
<li>Discuss cyberbullying — what it is and what to do</li>
<li>No social media accounts before 13 (legal requirement)</li>
</ul>

<h2>Ages 13+: Building Digital Literacy</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Have open conversations about online risks</li>
<li>Teach about phishing, scams, and fake news</li>
<li>Review privacy settings together on social media</li>
<li>Discuss the permanence of online posts</li>
<li>Model good digital behavior yourself</li>
</ul>

<h2>Apps to Check</h2>
<p style="font-size:14px;color:#374151">Use Nerq to check any app: <a href="/is-roblox-safe-for-kids" style="color:#0d9488">Roblox</a> · <a href="/is-tiktok-safe-for-kids" style="color:#0d9488">TikTok</a> · <a href="/is-discord-safe-for-kids" style="color:#0d9488">Discord</a> · <a href="/is-fortnite-safe-for-kids" style="color:#0d9488">Fortnite</a> · <a href="/is-minecraft-safe-for-kids" style="color:#0d9488">Minecraft</a></p>
"""},

    "online-shopping-safety": {
        "title": f"Online Shopping Safety Checklist {YEAR}",
        "desc": f"How to shop online safely. Verify stores, protect payments, avoid scams. Trust-checked guide. Updated {MY}.",
        "content": f"""
<h1>Online Shopping Safety Checklist {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Online shopping fraud costs consumers billions. Use this checklist before every purchase to protect yourself.</p>

<h2>Before You Buy</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Check the website trust score</strong> — Use nerq.ai/is-[store]-safe-to-buy-from</li>
<li><strong>Look for HTTPS</strong> — Never enter payment info on HTTP sites</li>
<li><strong>Check domain age</strong> — New domains (< 6 months) are high risk</li>
<li><strong>Read reviews on independent sites</strong> — Not just on the store itself</li>
<li><strong>Verify contact information</strong> — Real phone number, physical address, real email</li>
<li><strong>Check return policy</strong> — Legitimate stores have clear return policies</li>
<li><strong>Use a credit card</strong> — Better fraud protection than debit cards</li>
</ol>

<h2>Red Flags</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Prices 70-90% below retail (too good to be true)</li>
<li>Only accepts wire transfer, crypto, or gift cards</li>
<li>No customer service phone number</li>
<li>Poor website design with broken images</li>
<li>Countdown timers creating false urgency</li>
</ul>
"""},

    "best-free-antivirus": {
        "title": f"Best Free Antivirus {YEAR} — Trust Ranked",
        "desc": f"Best free antivirus software ranked by Nerq Trust Score. Independent analysis, no affiliate links. Updated {MY}.",
        "content": f"""
<h1>Best Free Antivirus {YEAR} — Trust Ranked</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Free antivirus software ranked by independent Nerq Trust Score. No affiliate links. Based on security effectiveness, privacy practices, and system impact.</p>

<h2>Top Free Antivirus (Trust Ranked)</h2>
<table>
<tr><th>#</th><th>Antivirus</th><th>Platform</th><th>Key Feature</th></tr>
<tr><td>1</td><td><a href="/is-windows-defender-safe" style="color:#0d9488">Windows Defender</a></td><td>Windows</td><td>Built-in, no install needed</td></tr>
<tr><td>2</td><td><a href="/is-malwarebytes-safe" style="color:#0d9488">Malwarebytes Free</a></td><td>All</td><td>On-demand scanning</td></tr>
<tr><td>3</td><td><a href="/is-bitdefender-safe" style="color:#0d9488">Bitdefender Free</a></td><td>Windows</td><td>Lightweight, automatic</td></tr>
<tr><td>4</td><td><a href="/is-avast-safe" style="color:#0d9488">Avast Free</a></td><td>All</td><td>Comprehensive protection</td></tr>
<tr><td>5</td><td><a href="/is-avg-safe" style="color:#0d9488">AVG Free</a></td><td>All</td><td>Web protection</td></tr>
</table>
<p style="font-size:13px;color:#6b7280;margin-top:8px">Rankings based on Nerq Trust Score. No affiliate links. Independent analysis.</p>

<h2>Do You Even Need Antivirus?</h2>
<p style="font-size:14px;color:#374151">Windows Defender (built into Windows 10/11) provides adequate protection for most users. Consider additional antivirus if you frequently download files from untrusted sources or click email links.</p>
"""},

    "is-exe-safe": {
        "title": f"Is .exe Safe to Open? File Safety Guide {YEAR}",
        "desc": f"Should you open that .exe file? How to check if executable files are safe. Virus scanning guide. Updated {MY}.",
        "content": f"""
<h1>Is .exe Safe to Open? File Safety Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">.exe files can contain malware. Here's how to check if an executable file is safe before opening it.</p>

<h2>Before Opening Any .exe</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Check the source</strong> — Did you download it from the official website? Check the publisher at nerq.ai.</li>
<li><strong>Scan with antivirus</strong> — Right-click → "Scan with Windows Defender" or your antivirus</li>
<li><strong>Check VirusTotal</strong> — Upload the file to virustotal.com for a multi-engine scan</li>
<li><strong>Verify the digital signature</strong> — Right-click → Properties → Digital Signatures. Is it signed by a known publisher?</li>
<li><strong>Check the file size</strong> — Suspiciously small executables (< 100KB) may be downloaders for malware</li>
</ol>

<h2>High-Risk Sources</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Email attachments (even from known contacts)</li>
<li>Torrent downloads</li>
<li>"Cracked" or "free" versions of paid software</li>
<li>Pop-up download prompts on websites</li>
<li>USB drives from unknown sources</li>
</ul>

<h2>Safe Download Sources</h2>
<p style="font-size:14px;color:#374151">Always download from official websites. Check any software at: <code>nerq.ai/is-[software]-safe-to-download</code></p>
"""},

    "vpn-buying-guide": {
        "title": f"How to Choose a VPN — Independent Guide {YEAR}",
        "desc": f"Independent VPN buying guide. What to look for, red flags to avoid, and top recommendations ranked by trust. Updated {MY}.",
        "content": f"""
<h1>How to Choose a VPN — Independent Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">The VPN market is flooded with misleading affiliate reviews. This independent guide explains what actually matters when choosing a VPN, backed by data — not commissions. Updated {MY}.</p>

<h2>What to Look For in a VPN</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Not all VPNs are created equal. Here are the five critical factors that separate trustworthy VPNs from marketing machines.</p>

<h3>1. Jurisdiction</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>Why it matters:</strong> The country where a VPN is incorporated determines which laws govern your data. VPNs based in Five Eyes countries (US, UK, Canada, Australia, New Zealand) can be compelled to hand over data. Fourteen Eyes countries extend this surveillance network further. Look for VPNs based in privacy-friendly jurisdictions like <strong>Panama, Switzerland, the British Virgin Islands, or Romania</strong>. These countries have no mandatory data retention laws and are outside major intelligence-sharing alliances.</p>

<h3>2. Independent Audit Status</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>Why it matters:</strong> Any VPN can claim "no logs" — but claims without proof are worthless. The gold standard is a <strong>third-party audit by a reputable firm</strong> (Cure53, PricewaterhouseCoopers, Deloitte). Look for VPNs that have been audited multiple times, not just once. A single audit is a snapshot; recurring audits show ongoing commitment. Check whether the audit covers the full infrastructure (servers, code, policies) or just the privacy policy document.</p>

<h3>3. Logging Policy</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>What to check:</strong> Read the actual privacy policy, not the marketing page. A true no-logs VPN does not store connection timestamps, IP addresses, bandwidth usage, or browsing activity. Some VPNs claim "no logs" but still collect <strong>connection metadata</strong> (when you connected, how long, how much data). This metadata can be used to identify you. The best VPNs run on <strong>RAM-only servers</strong> that cannot store data persistently — if the server is seized or reboots, all data is wiped.</p>

<h3>4. Open Source Clients</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>Why it matters:</strong> Open source VPN clients can be independently verified by security researchers. If the code is closed source, you are trusting the company's claims blindly. VPNs like <strong>Mullvad, ProtonVPN, and WireGuard</strong> publish their source code. Open source also means faster vulnerability discovery and patching. Check whether the VPN uses proven protocols like <strong>WireGuard or OpenVPN</strong> rather than proprietary protocols that cannot be audited.</p>

<h3>5. Speed and Server Network</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">A VPN is only useful if it is fast enough for daily use. Key factors: number of server locations, server load balancing, protocol efficiency (WireGuard is typically 30-50% faster than OpenVPN), and whether the provider owns its servers or rents from third parties. <strong>Owned servers (bare metal)</strong> reduce the risk of third-party access to your data.</p>

<h2>Red Flags — VPNs to Avoid</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Free VPNs that sell your data:</strong> If you are not paying, you are the product. Many free VPNs have been caught selling browsing data to advertisers, injecting ads, or even containing malware. Research by CSIRO found that 38% of free Android VPN apps contained malware.</li>
<li><strong>Affiliate-driven "best VPN" review sites:</strong> Most top Google results for "best VPN" are affiliate sites earning 100%+ commission on first-year subscriptions. They rank VPNs by payout, not quality. Look for reviews from independent security researchers, not marketing sites.</li>
<li><strong>Lifetime subscriptions:</strong> VPN infrastructure costs money every month. A "lifetime" deal usually means the company will run out of money and either shut down or start monetizing your data.</li>
<li><strong>No published privacy policy:</strong> If a VPN does not have a clear, detailed privacy policy, do not use it.</li>
<li><strong>Based in China or Russia:</strong> VPNs in these jurisdictions are required to cooperate with government surveillance. Some "foreign" VPNs have been found to be secretly owned by Chinese companies.</li>
</ul>

<h2>Top VPN Recommendations</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Based on independent analysis — not affiliate commissions. Check full trust scores on Nerq:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong><a href="/vpn/mullvad" style="color:#0d9488">Mullvad VPN</a></strong> — Based in Sweden. Open source. Audited by Cure53. No email required to sign up. Accepts cash payments. EUR 5/month flat.</li>
<li><strong><a href="/vpn/protonvpn" style="color:#0d9488">ProtonVPN</a></strong> — Based in Switzerland. Open source. Audited. Free tier available without data limits. Strong integration with ProtonMail.</li>
<li><strong><a href="/vpn/ivpn" style="color:#0d9488">IVPN</a></strong> — Based in Gibraltar. Open source. Audited. Transparent ownership. No tracking on their website.</li>
<li><strong><a href="/vpn/nordvpn" style="color:#0d9488">NordVPN</a></strong> — Based in Panama. Audited by PwC and Deloitte. Large server network. Proprietary NordLynx protocol based on WireGuard.</li>
<li><strong><a href="/vpn/expressvpn" style="color:#0d9488">ExpressVPN</a></strong> — Based in British Virgin Islands. Audited by Cure53 and KPMG. RAM-only servers (TrustedServer technology).</li>
</ol>

<h2>How to Test Your VPN</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Connect to your VPN and visit <strong>ipleak.net</strong> — your real IP should not appear</li>
<li>Check for <strong>DNS leaks</strong> at dnsleaktest.com — all DNS requests should go through the VPN</li>
<li>Check for <strong>WebRTC leaks</strong> — some browsers leak your real IP even with a VPN active</li>
<li>Run a speed test before and after connecting — a good VPN should retain 70%+ of your base speed</li>
<li>Test the kill switch by disconnecting the VPN mid-download — traffic should stop completely</li>
</ol>

<h2>VPN vs Other Privacy Tools</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">A VPN is one layer of privacy, not a complete solution. It hides your IP from websites and your browsing from your ISP, but it does not make you anonymous. For stronger privacy, combine a VPN with a <a href="/guide/stop-being-tracked-online" style="color:#0d9488">privacy-focused browser</a>, <a href="/guide/private-browsing-guide" style="color:#0d9488">private search engines</a>, and good security hygiene. Tor provides stronger anonymity but is significantly slower.</p>

<p style="font-size:14px;color:#374151;line-height:1.8">Browse all VPN trust scores at <a href="/vpn" style="color:#0d9488">nerq.ai/vpn</a>.</p>
"""},

    "safe-browser-extensions": {
        "title": f"Browser Extension Safety — What Permissions to Watch For {YEAR}",
        "desc": f"How to audit browser extension permissions. Dangerous permissions explained, Chrome vs Firefox models, stay safe. Updated {MY}.",
        "content": f"""
<h1>Browser Extension Safety — What Permissions to Watch For {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Browser extensions can read everything you type, see every website you visit, and steal your passwords. This guide explains how to audit extension permissions and stay safe. Updated {MY}.</p>

<h2>Why Browser Extensions Are Dangerous</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Browser extensions run inside your browser with elevated privileges. A malicious or compromised extension can <strong>read your passwords as you type them</strong>, steal banking session cookies, inject ads into every page, redirect your searches, and exfiltrate your browsing history. In {YEAR} alone, multiple popular extensions with millions of users were found to be secretly collecting and selling browsing data. The risk is real and underestimated by most users.</p>

<h2>Dangerous Permissions to Watch For</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">When you install an extension, it requests permissions. Here are the most dangerous ones:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>"Read and change all your data on all websites"</strong> — This is the most dangerous permission. It gives the extension full access to every website you visit, including banking sites, email, and social media. Only grant this to extensions you absolutely trust and need.</li>
<li><strong>"Read and change your browsing history"</strong> — The extension can see every site you have ever visited and delete or modify history entries.</li>
<li><strong>"Manage your downloads"</strong> — Can download files to your computer without your knowledge. Malware delivery vector.</li>
<li><strong>"Modify data you copy and paste"</strong> — Can intercept clipboard content. Crypto address swapping attacks use this to replace wallet addresses.</li>
<li><strong>"Read and modify cookies"</strong> — Can steal session cookies to hijack your logged-in accounts without needing your password.</li>
<li><strong>"Communicate with cooperating native applications"</strong> — Can execute programs on your computer outside the browser sandbox.</li>
<li><strong>"Change your privacy-related settings"</strong> — Can disable security features, change your proxy settings, or modify DNS.</li>
</ol>

<h2>How to Audit Your Extensions</h2>
<h3>Chrome</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <code>chrome://extensions</code></li>
<li>Click "Details" on each extension to see its permissions</li>
<li>Click "Site access" to control which sites the extension can access</li>
<li>Remove any extension you do not actively use — dormant extensions are still a risk</li>
<li>Set extensions to "On click" instead of "On all sites" where possible</li>
</ol>

<h3>Firefox</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <code>about:addons</code></li>
<li>Click on each extension and review "Permissions"</li>
<li>Firefox shows permissions more clearly than Chrome and requires explicit consent for each</li>
<li>Firefox extensions are reviewed by Mozilla staff before listing — but this is not foolproof</li>
</ol>

<h2>Chrome vs Firefox Permission Models</h2>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>Chrome</strong> uses Manifest V3, which limits background scripts and restricts some powerful APIs. However, Chrome still allows broad "all sites" access. Google reviews extensions algorithmically, which means some malicious ones slip through. <strong>Firefox</strong> uses a more granular permission model and has human reviewers for listed extensions. Firefox also supports <strong>container tabs</strong> that isolate extension access per tab, adding an extra layer of security. For privacy-conscious users, Firefox generally offers better extension security controls.</p>

<h2>Safe Extension Practices</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Minimize extensions:</strong> Every extension is an attack surface. Only install what you truly need.</li>
<li><strong>Check the publisher:</strong> Is the developer a known company or individual? Check their website and reputation.</li>
<li><strong>Read recent reviews:</strong> Look for reviews mentioning unexpected behavior, ads, or slowness. A previously safe extension can go rogue after being sold to a new owner.</li>
<li><strong>Check update frequency:</strong> Extensions that haven't been updated in over a year may be abandoned and vulnerable.</li>
<li><strong>Use open source extensions:</strong> Extensions with public source code (e.g., uBlock Origin, Bitwarden) can be verified by the community.</li>
<li><strong>Watch for ownership changes:</strong> Popular extensions are sometimes bought by companies that inject ads or tracking. If an extension suddenly asks for new permissions after an update, investigate before accepting.</li>
</ul>

<h2>Recommended Safe Extensions</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>uBlock Origin</strong> — Open source ad/tracker blocker. Does not "accept acceptable ads." Lightweight.</li>
<li><strong>Bitwarden</strong> — Open source password manager extension. Audited. Cross-platform.</li>
<li><strong>HTTPS Everywhere</strong> — Forces HTTPS connections (now largely built into browsers).</li>
<li><strong>Privacy Badger</strong> — EFF's tracker blocker. Learns tracking behavior automatically.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">Check any extension's trust score at <a href="/extensions" style="color:#0d9488">nerq.ai/extensions</a>.</p>
"""},

    "wordpress-security-guide": {
        "title": f"WordPress Security Guide {YEAR}",
        "desc": f"Complete WordPress security guide. Protect your site from hackers, plugin vulnerabilities, and brute force attacks. Updated {MY}.",
        "content": f"""
<h1>WordPress Security Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">WordPress powers 43% of all websites, making it the #1 target for hackers. Most WordPress hacks exploit outdated plugins, weak passwords, and missing security basics. This guide covers everything you need to secure your site. Updated {MY}.</p>

<h2>1. Keep WordPress Core Updated</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">WordPress releases security patches regularly. Running an outdated version is the single biggest risk factor. <strong>Enable automatic updates</strong> for minor releases (security patches) at minimum. Major version updates should be tested on a staging site first, then applied within a week. As of {YEAR}, any site running WordPress 5.x or below is critically vulnerable. Check your version at Dashboard → Updates.</p>

<h2>2. Plugin Vulnerabilities — The #1 Attack Vector</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Over 90% of WordPress vulnerabilities come from plugins, not WordPress core. Here is how to manage plugin risk:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Audit your plugins monthly:</strong> Remove any plugin you are not actively using. Deactivated plugins are still a risk if their files exist on the server.</li>
<li><strong>Check plugin reputation before installing:</strong> Look for active development (updated within 3 months), high install count (50K+), and good ratings. Check trust scores at <a href="/wordpress-plugins" style="color:#0d9488">nerq.ai/wordpress-plugins</a>.</li>
<li><strong>Never use nulled (pirated) plugins:</strong> They almost always contain backdoors and malware.</li>
<li><strong>Enable auto-updates for plugins:</strong> Go to Plugins → click "Enable auto-updates" for each plugin.</li>
<li><strong>Subscribe to vulnerability feeds:</strong> WPScan and Patchstack publish WordPress vulnerability databases. Monitor them for plugins you use.</li>
</ol>

<h2>3. Strong Passwords and User Management</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Use a password manager</strong> to generate unique, random passwords for every WordPress account</li>
<li><strong>Never use "admin" as a username</strong> — it is the first username brute-force bots try</li>
<li><strong>Enable two-factor authentication (2FA)</strong> for all admin and editor accounts</li>
<li><strong>Limit login attempts</strong> — install a plugin like Limit Login Attempts Reloaded to block brute force</li>
<li><strong>Audit user accounts quarterly:</strong> Remove inactive users, especially those with admin or editor roles</li>
<li><strong>Use strong passwords for FTP, database, and hosting panel</strong> — not just WordPress itself</li>
</ul>

<h2>4. Security Plugins</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">A security plugin adds firewall rules, malware scanning, and login protection. Recommended options:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Wordfence</strong> — Firewall + malware scanner. Free tier is solid. Blocks malicious IPs in real-time.</li>
<li><strong>Sucuri Security</strong> — Cloud-based WAF (Web Application Firewall). Particularly good for DDoS protection.</li>
<li><strong>iThemes Security</strong> — User-friendly. Good for non-technical site owners. Enforces strong passwords and 2FA.</li>
<li><strong>Patchstack</strong> — Focused on virtual patching for plugin vulnerabilities. Auto-patches known vulns before plugin authors release fixes.</li>
</ol>

<h2>5. Backup Strategy</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">If your site is hacked, a clean backup is your insurance policy. Follow the 3-2-1 rule:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>3 copies</strong> of your data (live site + 2 backups)</li>
<li><strong>2 different storage types</strong> (e.g., local + cloud)</li>
<li><strong>1 offsite backup</strong> (not on the same server as your site)</li>
<li>Use <strong>UpdraftPlus</strong> or <strong>BlogVault</strong> for automated daily backups to cloud storage (Google Drive, S3, Dropbox)</li>
<li>Test your backups quarterly by restoring to a staging site</li>
<li>Keep at least 30 days of backup history so you can restore from before a compromise</li>
</ul>

<h2>6. Server-Level Hardening</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Disable file editing in WordPress: add <code>define('DISALLOW_FILE_EDIT', true);</code> to wp-config.php</li>
<li>Protect wp-config.php: move it one directory above web root or restrict access via .htaccess</li>
<li>Disable XML-RPC if not needed: it is a common brute-force target</li>
<li>Set correct file permissions: directories 755, files 644, wp-config.php 440</li>
<li>Use HTTPS everywhere: install a free SSL certificate via Let's Encrypt</li>
<li>Hide your WordPress version number from source code</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">Check WordPress plugin trust scores at <a href="/wordpress-plugins" style="color:#0d9488">nerq.ai/wordpress-plugins</a>.</p>
"""},

    "safe-games-for-kids": {
        "title": f"Safe Games for Kids — Parent Guide {YEAR}",
        "desc": f"Parent guide to safe games for kids. Age ratings explained, microtransaction risks, recommended safe games by age. Updated {MY}.",
        "content": f"""
<h1>Safe Games for Kids — Parent Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Not all games marketed to children are safe for children. This guide helps parents understand age ratings, identify hidden risks, and choose genuinely safe games for every age group. Updated {MY}.</p>

<h2>Understanding Age Ratings</h2>
<h3>ESRB (North America)</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">The Entertainment Software Rating Board assigns ratings to games sold in the US and Canada:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>E (Everyone):</strong> Suitable for all ages. May contain minimal cartoon violence and mild language.</li>
<li><strong>E10+ (Everyone 10+):</strong> More cartoon or fantasy violence, mild language, minimal suggestive themes.</li>
<li><strong>T (Teen, 13+):</strong> Violence, suggestive themes, crude humor, minimal blood, simulated gambling, infrequent strong language.</li>
<li><strong>M (Mature, 17+):</strong> Intense violence, blood and gore, sexual content, strong language. Not for children.</li>
</ul>

<h3>PEGI (Europe)</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Pan European Game Information uses age labels: <strong>PEGI 3, PEGI 7, PEGI 12, PEGI 16, PEGI 18</strong>. PEGI also uses content descriptors: violence, bad language, fear, gambling, sex, drugs, discrimination, and in-game purchases. These descriptors appear as icons on the game box or store listing.</p>

<h2>Hidden Risks in Kids' Games</h2>
<h3>Microtransactions and Loot Boxes</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Many free-to-play games aimed at children use aggressive microtransaction systems. Children may not understand they are spending real money. <strong>Loot boxes</strong> — randomized rewards purchased with real money — function like gambling and are banned in some countries (Belgium, Netherlands). Watch for games that create artificial waiting times, social pressure to buy cosmetics, or "pay to win" mechanics.</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Disable in-app purchases</strong> on your child's device (iOS: Settings → Screen Time → Content Restrictions; Android: Google Play → Settings → Authentication)</li>
<li>Set spending limits on gaming accounts</li>
<li>Review purchase history regularly</li>
</ul>

<h3>Chat and Social Features</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Online multiplayer games often include text chat, voice chat, and friend systems. Risks include <strong>contact from strangers, cyberbullying, exposure to inappropriate language, and grooming</strong>. Many parents do not realize that "kids' games" like Roblox allow open chat with adult strangers by default.</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Disable chat features or set to "friends only"</li>
<li>Review friend lists regularly</li>
<li>Use parental controls to restrict voice chat</li>
<li>Teach children never to share personal information in games</li>
</ul>

<h2>Recommended Safe Games by Age</h2>
<h3>Ages 3-5</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><a href="/game/sago-mini" style="color:#0d9488">Sago Mini games</a> — No ads, no in-app purchases, designed by child development experts</li>
<li><a href="/game/toca-boca" style="color:#0d9488">Toca Boca series</a> — Open-ended creative play, no competition, no chat</li>
<li><a href="/game/sesame-street" style="color:#0d9488">Sesame Street games</a> — Educational, no microtransactions</li>
</ul>

<h3>Ages 6-8</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><a href="/is-minecraft-safe-for-kids" style="color:#0d9488">Minecraft</a> (Creative mode, offline) — Building and creativity. Disable online multiplayer for younger children.</li>
<li><a href="/game/mario" style="color:#0d9488">Super Mario series</a> — No microtransactions, no online chat, no ads</li>
<li><a href="/game/pokemon" style="color:#0d9488">Pokemon games</a> (console) — Turn-based, no real-money gambling, mild cartoon violence</li>
</ul>

<h3>Ages 9-12</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><a href="/is-roblox-safe-for-kids" style="color:#0d9488">Roblox</a> — Popular but requires parental controls. Enable account restrictions and disable chat.</li>
<li><a href="/is-fortnite-safe-for-kids" style="color:#0d9488">Fortnite</a> — Rated T (13+). Cartoon violence. Aggressive microtransactions. Set spending limits.</li>
<li><a href="/game/zelda" style="color:#0d9488">Zelda series</a> — Adventure/puzzle with mild fantasy violence. No online features.</li>
</ul>

<h2>Setting Up Parental Controls</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Every gaming platform has parental controls. Set them up before giving the device to your child:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Nintendo Switch:</strong> Nintendo Switch Parental Controls app — set play time limits, restrict online features, restrict games by age rating</li>
<li><strong>PlayStation:</strong> Family Management on PS4/PS5 — spending limits, communication restrictions, game age limits</li>
<li><strong>Xbox:</strong> Microsoft Family Safety app — screen time, content filters, spending controls</li>
<li><strong>PC:</strong> Use platform-specific controls (Steam Family View, Epic parental controls)</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">See also: <a href="/guide/parental-controls-guide" style="color:#0d9488">Complete Parental Controls Guide</a> and <a href="/guide/internet-safety-for-kids" style="color:#0d9488">Internet Safety for Kids</a>.</p>
"""},

    "parental-controls-guide": {
        "title": f"Parental Controls Guide — Every Device {YEAR}",
        "desc": f"Step-by-step parental controls setup for iOS, Android, Windows, Mac, gaming consoles, and routers. Updated {MY}.",
        "content": f"""
<h1>Parental Controls Guide — Every Device {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Every major platform has built-in parental controls, but most parents never set them up. This step-by-step guide covers every device your child might use. Updated {MY}.</p>

<h2>iOS / iPhone / iPad — Screen Time</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Apple's Screen Time is the most comprehensive built-in parental control system available. Here is how to set it up:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Screen Time</strong></li>
<li>Tap <strong>"Turn On Screen Time"</strong> and select "This is My Child's iPhone/iPad"</li>
<li>Set a <strong>Screen Time Passcode</strong> (different from the device passcode — use a code your child cannot guess)</li>
<li><strong>Downtime:</strong> Schedule hours when only allowed apps work (e.g., 9 PM to 7 AM)</li>
<li><strong>App Limits:</strong> Set daily time limits per app category (e.g., 1 hour for Games, 30 min for Social)</li>
<li><strong>Content & Privacy Restrictions:</strong> Block explicit content, prevent app installs/deletes, disable in-app purchases</li>
<li><strong>Communication Limits:</strong> Control who your child can call, text, and FaceTime during allowed and downtime hours</li>
<li>Enable <strong>"Share Across Devices"</strong> if your child uses multiple Apple devices</li>
</ol>

<h2>Android — Google Family Link</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Install the <strong>Google Family Link</strong> app on your phone and your child's phone</li>
<li>Create a <strong>Google Account for your child</strong> (supervised account for under 13)</li>
<li>Set <strong>daily screen time limits</strong> and a bedtime schedule</li>
<li>Approve or block <strong>app downloads</strong> from Google Play — you get a notification for each request</li>
<li>Set <strong>content filters</strong> for Google Play (apps, games, movies, books by age rating)</li>
<li>Enable <strong>Google SafeSearch</strong> to filter explicit search results</li>
<li>Use <strong>location tracking</strong> to see your child's device location</li>
<li>Lock the device remotely when it is time to stop</li>
</ol>

<h2>Windows — Microsoft Family Safety</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Create a <strong>child account</strong> at family.microsoft.com</li>
<li>Sign in to the child account on the Windows PC</li>
<li>Set <strong>screen time limits</strong> per device and per day of the week</li>
<li>Enable <strong>web filtering</strong> in Microsoft Edge (block specific sites or allow only approved sites)</li>
<li>Set <strong>app and game limits</strong> by age rating</li>
<li>Enable <strong>activity reporting</strong> to see which apps and websites your child uses</li>
<li>Set <strong>spending limits</strong> for the Microsoft Store</li>
</ol>

<h2>Mac — Screen Time (macOS)</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>System Settings → Screen Time</strong></li>
<li>If using Family Sharing, select your child's account</li>
<li>Configure <strong>App Limits, Downtime, Communication Limits</strong> (same options as iOS)</li>
<li>Under <strong>Content & Privacy</strong>, restrict web content, explicit content, and app installs</li>
<li>Settings sync with iOS if the child uses both an iPhone and a Mac</li>
</ol>

<h2>Gaming Consoles</h2>
<h3>Nintendo Switch</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Download the <strong>Nintendo Switch Parental Controls</strong> app on your phone</li>
<li>Set daily play time limits (alarm or forced suspension)</li>
<li>Restrict games by age rating (ESRB/PEGI)</li>
<li>Disable communication with other players</li>
<li>Disable posting to social media</li>
</ul>

<h3>PlayStation (PS4/PS5)</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Family Management</strong> and create a child account</li>
<li>Set age level for games, Blu-ray/DVD, and web browsing</li>
<li>Restrict communication (messages, voice chat, user-generated content)</li>
<li>Set monthly spending limits on PlayStation Store</li>
<li>Control play time via PlayStation Family Management website or app</li>
</ul>

<h3>Xbox</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Use the <strong>Xbox Family Settings</strong> app or family.microsoft.com</li>
<li>Set screen time limits per day</li>
<li>Filter content by age rating</li>
<li>Manage friend requests and online communication</li>
<li>Approve purchases and set spending limits</li>
</ul>

<h2>Router-Level Controls</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">For whole-home protection that covers every device (including smart TVs and IoT devices):</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>OpenDNS FamilyShield:</strong> Free. Set your router's DNS to 208.67.222.123 and 208.67.220.123 to block adult content network-wide.</li>
<li><strong>CleanBrowsing:</strong> Free DNS-based filtering with family, adult, and security filter levels.</li>
<li><strong>Router admin panel:</strong> Most modern routers (Netgear, Asus, TP-Link) have built-in parental controls with scheduling and website blocking. Log in at 192.168.1.1 or your router's gateway address.</li>
<li><strong>Pi-hole:</strong> Advanced. Network-wide ad and tracker blocker. Requires a Raspberry Pi or similar device.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">See also: <a href="/guide/safe-games-for-kids" style="color:#0d9488">Safe Games for Kids</a> · <a href="/guide/safe-apps-for-children" style="color:#0d9488">Safe Apps for Children</a> · <a href="/guide/internet-safety-for-kids" style="color:#0d9488">Internet Safety for Kids</a>.</p>
"""},

    "safe-apps-for-children": {
        "title": f"Safe Apps for Children — Age-Appropriate Guide {YEAR}",
        "desc": f"Age-appropriate safe apps for children. COPPA compliance, no ads, no chat. Recommendations for ages 3-12. Updated {MY}.",
        "content": f"""
<h1>Safe Apps for Children — Age-Appropriate Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Finding truly safe apps for kids is harder than it should be. Many apps marketed to children contain ads, in-app purchases, data collection, and unmoderated chat features. This guide identifies what makes an app genuinely safe and recommends the best options by age group. Updated {MY}.</p>

<h2>What Makes an App Safe for Children?</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">A safe children's app should meet all of the following criteria:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>No advertising:</strong> Children cannot distinguish ads from content. Ads in kids' apps often lead to inappropriate content or app store pages for adult apps.</li>
<li><strong>No unmoderated chat:</strong> Any social or chat features must be heavily moderated or disabled entirely. Open chat with strangers is never acceptable in a children's app.</li>
<li><strong>COPPA compliant:</strong> The Children's Online Privacy Protection Act (US) requires apps directed at children under 13 to obtain parental consent before collecting personal information. In the EU, GDPR-K sets similar requirements. Check the app's privacy policy for explicit COPPA/GDPR compliance statements.</li>
<li><strong>No manipulative design:</strong> Loot boxes, countdown timers, "streak" mechanics, and social pressure tactics are manipulative. A safe app does not use psychological tricks to keep children engaged beyond healthy limits.</li>
<li><strong>Age-appropriate content:</strong> The app should be designed for the specific age range, not just "kid-friendly" as an afterthought.</li>
<li><strong>Transparent data practices:</strong> The app should clearly state what data it collects (ideally none beyond what is necessary for functionality) and never share children's data with third-party advertisers.</li>
</ul>

<h2>Recommended Safe Apps: Ages 3-5</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">At this age, apps should be simple, educational, and completely free of social features:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong><a href="/is-sago-mini-safe-for-kids" style="color:#0d9488">Sago Mini World</a></strong> — Subscription-based (no individual purchases). 40+ games designed by child development experts. No ads, no chat, no data collection. Winner of multiple Parents' Choice awards.</li>
<li><strong><a href="/is-toca-boca-safe-for-kids" style="color:#0d9488">Toca Boca apps</a></strong> — Open-ended creative play. No winning or losing, no time pressure. Some apps are free with ads (avoid these); the paid versions are ad-free.</li>
<li><strong><a href="/is-pbs-kids-safe-for-kids" style="color:#0d9488">PBS Kids Games</a></strong> — Free, no ads, educational. Based on popular PBS shows. COPPA compliant.</li>
<li><strong>Khan Academy Kids</strong> — Free, no ads, no in-app purchases. Covers reading, math, and social-emotional learning. Excellent for pre-K through 1st grade.</li>
<li><strong>Busy Shapes</strong> — Simple shape-sorting puzzles. No text needed, no ads, no social features.</li>
</ul>

<h2>Recommended Safe Apps: Ages 6-8</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong><a href="/is-scratch-jr-safe-for-kids" style="color:#0d9488">ScratchJr</a></strong> — Free coding app from MIT. Children create interactive stories and games using visual blocks. No ads, no social features, no data collection.</li>
<li><strong><a href="/is-minecraft-safe-for-kids" style="color:#0d9488">Minecraft Education</a></strong> — School-focused version of Minecraft. Controlled multiplayer, lesson plans, no public servers.</li>
<li><strong>Prodigy Math</strong> — Math practice disguised as an RPG. Free core game. Paid premium removes some limitations. Monitor for microtransaction requests.</li>
<li><strong>Duolingo ABC</strong> — Free reading and writing app. No ads. From the trusted Duolingo team.</li>
<li><strong>Lightbot</strong> — Programming puzzles. No ads, no social features, no data collection. One-time purchase.</li>
</ul>

<h2>Recommended Safe Apps: Ages 9-12</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong><a href="/is-scratch-safe-for-kids" style="color:#0d9488">Scratch</a></strong> — MIT's coding platform. Moderated community. Children can create and share projects. Active moderation team reviews content.</li>
<li><strong><a href="/is-duolingo-safe-for-kids" style="color:#0d9488">Duolingo</a></strong> — Language learning. Free with ads, or ad-free with subscription. No social chat between users.</li>
<li><strong>GarageBand</strong> — Music creation. No social features, no ads, free on Apple devices.</li>
<li><strong>Google Earth</strong> — Explore the world. No ads, no social features. Educational and engaging.</li>
<li><strong><a href="/is-khan-academy-safe-for-kids" style="color:#0d9488">Khan Academy</a></strong> — Free educational content covering math, science, history, and more. No ads, no social features.</li>
</ul>

<h2>Apps to Approach with Caution</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">These popular apps are not necessarily unsafe but require parental supervision and configuration:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong><a href="/is-youtube-kids-safe-for-kids" style="color:#0d9488">YouTube Kids</a>:</strong> Filtered version of YouTube, but inappropriate content still slips through algorithmic filters. Use "Approved content only" mode.</li>
<li><strong><a href="/is-roblox-safe-for-kids" style="color:#0d9488">Roblox</a>:</strong> Massive platform with user-generated games. Some games are excellent; others contain inappropriate content. Enable Account Restrictions and review games before allowing play.</li>
<li><strong><a href="/is-discord-safe-for-kids" style="color:#0d9488">Discord</a>:</strong> Rated 13+. Open chat with strangers. Not recommended for children under 13 regardless of parental controls.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">Check any app's safety at <code>nerq.ai/is-[app]-safe-for-kids</code>. See also: <a href="/guide/parental-controls-guide" style="color:#0d9488">Parental Controls Guide</a>.</p>
"""},

    "password-safety": {
        "title": f"Password Safety Guide {YEAR}",
        "desc": f"Password manager comparison, how long to crack passwords, passkeys explained, 2FA setup. Complete guide. Updated {MY}.",
        "content": f"""
<h1>Password Safety Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Weak and reused passwords are the cause of over 80% of data breaches. This guide covers everything you need to know about password security in {YEAR}, including password managers, passkeys, and two-factor authentication. Updated {MY}.</p>

<h2>How Long Does It Take to Crack Your Password?</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Modern GPUs can test billions of password combinations per second. Here is how long different password types take to crack with current hardware:</p>
<table>
<tr><th>Password Type</th><th>Example</th><th>Time to Crack</th></tr>
<tr><td>6 characters, lowercase</td><td>pizza1</td><td>Instant</td></tr>
<tr><td>8 characters, mixed case</td><td>PizzA12!</td><td>~8 hours</td></tr>
<tr><td>12 characters, mixed</td><td>MyP!zza2026x</td><td>~3,000 years</td></tr>
<tr><td>16 characters, random</td><td>kX9!mP2@nQ5$rT8&</td><td>Trillions of years</td></tr>
<tr><td>4-word passphrase</td><td>correct-horse-battery-staple</td><td>~550 years</td></tr>
</table>
<p style="font-size:13px;color:#6b7280">Estimates based on offline brute-force attack with modern GPU clusters. Online attacks are slower due to rate limiting.</p>

<h2>Password Manager Comparison</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">A password manager generates, stores, and auto-fills unique passwords for every account. You only need to remember one master password. Here are the top options:</p>
<table>
<tr><th>Manager</th><th>Price</th><th>Open Source</th><th>Audited</th><th>Best For</th></tr>
<tr><td><strong>Bitwarden</strong></td><td>Free / $10/yr</td><td>Yes</td><td>Yes (Cure53)</td><td>Best overall. Free tier is generous.</td></tr>
<tr><td><strong>1Password</strong></td><td>$36/yr</td><td>No</td><td>Yes</td><td>Best for families. Polished UI.</td></tr>
<tr><td><strong>KeePass</strong></td><td>Free</td><td>Yes</td><td>Yes (EU-FOSSA)</td><td>Maximum control. Local-only storage.</td></tr>
<tr><td><strong>Proton Pass</strong></td><td>Free / $48/yr</td><td>Yes</td><td>Yes</td><td>Privacy-focused. Integrated with ProtonMail.</td></tr>
<tr><td><strong>Apple Keychain</strong></td><td>Free</td><td>No</td><td>No</td><td>Apple-only users. Built-in. Passkey support.</td></tr>
</table>

<h2>Passkeys Explained</h2>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>Passkeys</strong> are the future of authentication. They replace passwords entirely with cryptographic key pairs stored on your device. Here is what you need to know:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>How they work:</strong> When you create a passkey, your device generates a public-private key pair. The public key goes to the website; the private key stays on your device, protected by biometrics (Face ID, fingerprint) or your device PIN.</li>
<li><strong>Phishing-proof:</strong> Passkeys are bound to the specific website domain. A phishing site cannot trick you into using your passkey because the domain will not match.</li>
<li><strong>No password to steal:</strong> There is no password stored on the server that can be leaked in a data breach.</li>
<li><strong>Cross-device sync:</strong> Apple syncs passkeys via iCloud Keychain. Google syncs via Google Password Manager. 1Password and Bitwarden also support passkey storage.</li>
<li><strong>Adoption in {YEAR}:</strong> Google, Apple, Microsoft, Amazon, GitHub, PayPal, and many major services now support passkeys. Adoption is growing rapidly.</li>
</ul>

<h2>Setting Up Two-Factor Authentication (2FA)</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Even with a strong password, enable 2FA on every account that supports it. See our dedicated <a href="/guide/two-factor-authentication" style="color:#0d9488">2FA guide</a> for detailed instructions. Quick summary:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Best:</strong> Hardware security key (YubiKey, Google Titan) — phishing-proof</li>
<li><strong>Good:</strong> Authenticator app (Authy, Google Authenticator, Microsoft Authenticator)</li>
<li><strong>Acceptable:</strong> SMS-based 2FA — better than nothing, but vulnerable to SIM swapping</li>
</ol>

<h2>Password Rules That Actually Work</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Never reuse passwords.</strong> If one service is breached, every account with that password is compromised.</li>
<li><strong>Length beats complexity.</strong> "correct-horse-battery-staple" is stronger and easier to remember than "P@$$w0rd!"</li>
<li><strong>Use a password manager.</strong> Humans cannot generate or remember truly random passwords for 100+ accounts.</li>
<li><strong>Check for breaches.</strong> Use <a href="/guide/how-to-check-for-data-breach" style="color:#0d9488">haveibeenpwned.com</a> to check if your passwords have been leaked.</li>
<li><strong>Change passwords only when breached.</strong> Mandatory rotation every 90 days leads to weaker passwords (NIST now recommends against forced rotation).</li>
<li><strong>Use passkeys where available.</strong> They are more secure and more convenient than passwords.</li>
</ul>
"""},

    "two-factor-authentication": {
        "title": f"Two-Factor Authentication (2FA) Guide {YEAR}",
        "desc": f"Complete 2FA guide. SMS vs authenticator app vs hardware key. Setup instructions for major services. Updated {MY}.",
        "content": f"""
<h1>Two-Factor Authentication (2FA) Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Two-factor authentication adds a second layer of security beyond your password. Even if your password is stolen, an attacker cannot access your account without the second factor. This guide covers every 2FA method, setup instructions, and backup strategies. Updated {MY}.</p>

<h2>2FA Methods Compared</h2>
<h3>SMS-Based 2FA</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>How it works:</strong> A code is sent to your phone via text message. You enter the code to log in. <strong>Pros:</strong> Easy to set up, works on any phone, no app needed. <strong>Cons:</strong> Vulnerable to SIM swapping (attackers convince your carrier to transfer your number to their SIM), SS7 network attacks, and social engineering. <strong>Verdict:</strong> Better than no 2FA, but the weakest option. Use an authenticator app instead if possible.</p>

<h3>Authenticator App</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>How it works:</strong> An app on your phone generates a time-based one-time password (TOTP) that changes every 30 seconds. The code is generated locally — no network connection needed. <strong>Recommended apps:</strong></p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Authy</strong> — Cloud backup of 2FA tokens (encrypted). Multi-device sync. If you lose your phone, you can recover your codes.</li>
<li><strong>Google Authenticator</strong> — Simple, no account needed. Now supports cloud backup (opt-in). Previously local-only.</li>
<li><strong>Microsoft Authenticator</strong> — Good for Microsoft ecosystem. Supports push notifications for Microsoft accounts.</li>
<li><strong>Aegis (Android)</strong> — Open source, encrypted vault, local backups. Best for privacy-focused Android users.</li>
<li><strong>Raivo OTP (iOS)</strong> — Open source, native iOS app, iCloud sync.</li>
</ul>

<h3>Hardware Security Key</h3>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>How it works:</strong> A physical USB or NFC device (YubiKey, Google Titan, SoloKeys) that you plug in or tap when logging in. Uses FIDO2/WebAuthn protocol. <strong>Pros:</strong> Completely phishing-proof (the key verifies the website domain cryptographically), no codes to type, works offline. <strong>Cons:</strong> Costs $25-$70, need to carry it with you, need a backup key. <strong>Verdict:</strong> The most secure 2FA method. Recommended for high-value accounts (email, banking, crypto). Google requires all employees to use hardware keys, and phishing attacks against Google employees dropped to zero.</p>

<h2>Setup Instructions for Major Services</h2>
<h3>Google / Gmail</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to myaccount.google.com → Security → 2-Step Verification</li>
<li>Click "Get Started" and sign in</li>
<li>Choose your method: Google Prompts (easiest), Authenticator app, or Security key</li>
<li>Follow the on-screen setup — scan QR code for authenticator apps</li>
<li>Save backup codes in your password manager</li>
</ol>

<h3>Apple ID</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>On iPhone: Settings → [Your Name] → Sign-In & Security → Two-Factor Authentication</li>
<li>Apple uses trusted devices and phone numbers as second factors</li>
<li>Add a trusted phone number and enable hardware key support (iOS 16.3+)</li>
</ol>

<h3>Microsoft / Outlook</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to account.microsoft.com → Security → Advanced security options</li>
<li>Under "Additional security," turn on Two-step verification</li>
<li>Choose Microsoft Authenticator app, other authenticator, or security key</li>
</ol>

<h3>GitHub</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to Settings → Password and authentication → Two-factor authentication</li>
<li>GitHub now requires 2FA for all contributors. Use authenticator app or hardware key.</li>
<li>Save recovery codes securely</li>
</ol>

<h3>Banking and Financial Services</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Most banks offer SMS-based 2FA. Enable it even though SMS is the weakest option — for banking, any 2FA is far better than none. If your bank supports authenticator apps or hardware keys, use those instead. Check with your bank's security settings page.</p>

<h2>Recovery Codes — Your Safety Net</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">When you set up 2FA, most services give you <strong>recovery codes</strong> — one-time-use codes that let you in if you lose your 2FA device. These are critical:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Save them in your password manager</strong> (Bitwarden, 1Password — both have secure notes)</li>
<li><strong>Print a copy</strong> and store it somewhere safe (safe deposit box, locked drawer)</li>
<li><strong>Never save them in plain text</strong> on your computer or in cloud notes</li>
<li><strong>If you use up recovery codes, regenerate new ones</strong> immediately</li>
</ul>

<h2>Backup Strategy</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Use Authy or an app with cloud backup</strong> — so losing your phone does not lock you out of everything</li>
<li><strong>Register two hardware keys</strong> — keep one on your keychain and one in a safe location</li>
<li><strong>Save recovery codes for every service</strong> — test them periodically to ensure they work</li>
<li><strong>Keep your phone number updated</strong> on all accounts in case you need SMS fallback</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">See also: <a href="/guide/password-safety" style="color:#0d9488">Password Safety Guide</a> · <a href="/guide/what-to-do-if-hacked" style="color:#0d9488">What to Do If Hacked</a>.</p>
"""},

    "how-to-check-for-data-breach": {
        "title": f"Has Your Data Been Breached? How to Check {YEAR}",
        "desc": f"How to check if your data was exposed in a breach. HaveIBeenPwned, identity theft prevention, credit monitoring. Updated {MY}.",
        "content": f"""
<h1>Has Your Data Been Breached? How to Check {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Data breaches exposed over 8 billion records in the past year alone. Your email, passwords, and personal data may already be in criminal databases. Here is how to check and what to do about it. Updated {MY}.</p>

<h2>Step 1: Check HaveIBeenPwned</h2>
<p style="font-size:14px;color:#374151;line-height:1.8"><a href="https://haveibeenpwned.com" style="color:#0d9488" rel="nofollow"><strong>HaveIBeenPwned.com</strong></a> (HIBP) is a free service created by security researcher Troy Hunt. It aggregates data from known breaches and lets you search by email address or phone number.</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>haveibeenpwned.com</strong></li>
<li>Enter your email address and click "pwned?"</li>
<li>The site will show <strong>every known breach</strong> that included your email, along with what data was exposed (passwords, phone numbers, addresses, etc.)</li>
<li>Check <strong>all your email addresses</strong> — including old ones you no longer use</li>
<li>Sign up for <strong>breach notifications</strong> — HIBP will email you if your address appears in future breaches</li>
<li>Use the <strong>password checker</strong> at haveibeenpwned.com/Passwords to see if any of your passwords have appeared in known breaches (this is safe — it uses k-anonymity and does not send your full password)</li>
</ol>

<h2>Step 2: What to Do If You Are in a Breach</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">If your email appears in a breach, take these steps immediately:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Change the password</strong> for the breached service immediately. Use a <a href="/guide/password-safety" style="color:#0d9488">password manager</a> to generate a unique, random password.</li>
<li><strong>Change the password everywhere you reused it.</strong> If you used the same password on other sites (most people do), change it on all of them. This is why password reuse is so dangerous.</li>
<li><strong>Enable two-factor authentication</strong> on the breached account and all important accounts. See our <a href="/guide/two-factor-authentication" style="color:#0d9488">2FA guide</a>.</li>
<li><strong>Check for unauthorized access:</strong> Review recent login activity, connected apps, email forwarding rules, and recovery email/phone settings.</li>
<li><strong>Watch for phishing:</strong> After a breach, attackers often send targeted phishing emails using the stolen data. Be extra cautious of emails referencing the breached service.</li>
</ol>

<h2>Step 3: Identity Theft Prevention</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">If sensitive data was exposed (Social Security number, government ID, financial information), take additional steps:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Freeze your credit</strong> with all three bureaus (Equifax, Experian, TransUnion). This is free in the US and prevents anyone from opening new credit accounts in your name. You can temporarily lift the freeze when you need to apply for credit.</li>
<li><strong>Set up fraud alerts</strong> with the credit bureaus. A fraud alert requires creditors to verify your identity before opening new accounts.</li>
<li><strong>Monitor your credit report</strong> — you are entitled to free weekly reports from annualcreditreport.com.</li>
<li><strong>Consider identity theft protection services</strong> if government ID was exposed. Services like Identity Guard or LifeLock monitor dark web markets for your stolen data.</li>
<li><strong>File an identity theft report</strong> at identitytheft.gov (US) if you discover unauthorized activity.</li>
</ul>

<h2>Step 4: Credit Monitoring</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">After a major breach, set up ongoing monitoring:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Free credit monitoring:</strong> Many breached companies offer 1-2 years of free credit monitoring. Accept this offer — it typically includes dark web monitoring and identity theft insurance.</li>
<li><strong>Credit Karma:</strong> Free ongoing credit monitoring for TransUnion and Equifax.</li>
<li><strong>Bank alerts:</strong> Set up transaction alerts on all bank accounts and credit cards. Get notified of any charge over $1.</li>
<li><strong>IRS Identity Protection PIN:</strong> In the US, request an IP PIN from the IRS to prevent tax identity theft.</li>
</ul>

<h2>Other Breach Checking Tools</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Firefox Monitor:</strong> Mozilla's breach checker, powered by HIBP data. Integrated into Firefox browser.</li>
<li><strong>Google Password Checkup:</strong> Built into Chrome and Google Account settings. Checks saved passwords against known breaches.</li>
<li><strong>Apple Keychain breach detection:</strong> Built into iOS/macOS Settings → Passwords → Security Recommendations.</li>
<li><strong>1Password Watchtower:</strong> Checks all stored passwords against HIBP and flags compromised ones.</li>
<li><strong>Bitwarden Reports:</strong> Premium feature that checks vault passwords against known breaches.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">Check if specific services have been breached on Nerq: <code>nerq.ai/was-[service]-hacked</code>. See also: <a href="/guide/what-to-do-if-hacked" style="color:#0d9488">What to Do If Hacked</a>.</p>
"""},

    "stop-being-tracked-online": {
        "title": f"How to Stop Being Tracked Online {YEAR}",
        "desc": f"Complete guide to stop online tracking. Browser fingerprinting, cookies, VPNs, privacy browsers, DNS, ad blockers. Updated {MY}.",
        "content": f"""
<h1>How to Stop Being Tracked Online {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Every website you visit, every search you make, and every click you perform is tracked by dozens of companies. This guide explains how online tracking works and gives you practical steps to reduce it dramatically. Updated {MY}.</p>

<h2>How You Are Being Tracked</h2>
<h3>1. Tracking Cookies</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Third-party cookies are placed by advertising networks (Google, Meta, data brokers) across millions of websites. They follow you from site to site, building a detailed profile of your interests, purchases, health searches, political views, and more. While Chrome has delayed deprecating third-party cookies, <strong>Firefox and Safari already block them by default</strong>. Even without cookies, other tracking methods persist.</p>

<h3>2. Browser Fingerprinting</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Your browser reveals a unique combination of: screen resolution, installed fonts, timezone, language, installed plugins, hardware specs (GPU, CPU cores), canvas rendering, and WebGL output. Combined, these create a <strong>fingerprint that is unique to your device</strong> in 99%+ of cases. Unlike cookies, you cannot clear a fingerprint — it is derived from your device characteristics. This is the hardest form of tracking to defeat.</p>

<h3>3. IP Address Tracking</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Your IP address reveals your approximate location (city level), ISP, and can be used to link your activity across sites. Your ISP can see every website you visit (though not the content on HTTPS sites). A VPN hides your IP from websites and your browsing from your ISP.</p>

<h3>4. DNS Tracking</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Every time you visit a website, your device sends a DNS request (converting the domain name to an IP address). By default, these requests go to your ISP's DNS server — giving them a complete log of every site you visit, even with HTTPS. Using an encrypted DNS service prevents this.</p>

<h2>How to Reduce Tracking</h2>
<h3>Step 1: Switch to a Privacy-Focused Browser</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Brave:</strong> Chromium-based (compatible with Chrome extensions). Blocks ads and trackers by default. Fingerprinting protection. Built-in Tor windows. Best balance of privacy and usability.</li>
<li><strong>Firefox:</strong> Enhanced Tracking Protection blocks third-party cookies, fingerprinters, and cryptominers by default. Container tabs isolate sites. Open source, backed by Mozilla (non-profit).</li>
<li><strong>Tor Browser:</strong> Maximum anonymity. Routes traffic through 3 relays. All users have the same fingerprint. Very slow. Best for situations requiring true anonymity.</li>
<li><strong>Safari:</strong> Apple's Intelligent Tracking Prevention blocks cross-site tracking. Good default privacy for Apple users, though not as configurable as Firefox.</li>
</ul>

<h3>Step 2: Install an Ad/Tracker Blocker</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>uBlock Origin:</strong> The gold standard. Open source, lightweight, blocks ads and trackers. Available for Firefox and Chrome. Does not have an "acceptable ads" program (unlike Adblock Plus).</li>
<li><strong>Privacy Badger:</strong> EFF's tracker blocker. Automatically learns which domains track you. Complements uBlock Origin.</li>
</ul>

<h3>Step 3: Use a VPN</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">A VPN hides your IP address from websites and your browsing history from your ISP. Choose a trustworthy VPN — see our <a href="/guide/vpn-buying-guide" style="color:#0d9488">VPN buying guide</a>. Remember: a VPN does not make you anonymous by itself. The VPN provider can see your traffic instead of your ISP, so choose one with audited no-logs policies.</p>

<h3>Step 4: Switch to Encrypted DNS</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Cloudflare 1.1.1.1:</strong> Fast, private DNS. Does not sell data. Set as your system DNS or use their app.</li>
<li><strong>Quad9 (9.9.9.9):</strong> Non-profit DNS that also blocks known malicious domains. Privacy-focused.</li>
<li><strong>NextDNS:</strong> Customizable DNS with ad blocking, tracker blocking, and parental controls. Free tier available.</li>
<li>Enable <strong>DNS over HTTPS (DoH)</strong> or <strong>DNS over TLS (DoT)</strong> in your browser or OS settings to encrypt DNS queries.</li>
</ul>

<h3>Step 5: Reduce Your Digital Footprint</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Use email aliases:</strong> Services like SimpleLogin or Apple's Hide My Email create unique email addresses for each service. If one is breached or sold, you know exactly which service leaked it.</li>
<li><strong>Use privacy-focused search engines:</strong> <a href="/guide/private-browsing-guide" style="color:#0d9488">DuckDuckGo</a>, Startpage, or Brave Search do not track your searches.</li>
<li><strong>Review app permissions:</strong> See our <a href="/guide/most-private-phone-settings" style="color:#0d9488">private phone settings guide</a> to audit what your apps can access.</li>
<li><strong>Opt out of data brokers:</strong> Sites like DeleteMe and Privacy Duck help remove your personal information from data broker databases.</li>
<li><strong>Clear cookies regularly:</strong> Set your browser to clear cookies on exit, or use containers/profiles to isolate browsing sessions.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">For a complete privacy setup, combine this guide with our <a href="/guide/most-private-phone-settings" style="color:#0d9488">private phone settings</a> and <a href="/guide/private-browsing-guide" style="color:#0d9488">private browsing</a> guides.</p>
"""},

    "most-private-phone-settings": {
        "title": f"Most Private Phone Settings — iOS & Android {YEAR}",
        "desc": f"Step-by-step guide to the most private phone settings for iOS and Android. App permissions, location, ad tracking. Updated {MY}.",
        "content": f"""
<h1>Most Private Phone Settings — iOS & Android {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Your phone knows more about you than any other device — your location 24/7, your contacts, your photos, your health data, your browsing history. Here is how to lock it down. Updated {MY}.</p>

<h2>iOS Privacy Settings (iPhone/iPad)</h2>
<h3>1. Disable Ad Tracking</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Privacy & Security → Tracking</strong></li>
<li>Turn off <strong>"Allow Apps to Request to Track"</strong></li>
<li>This disables the IDFA (Identifier for Advertisers). Apps can no longer track you across other companies' apps and websites.</li>
</ol>

<h3>2. Limit Location Access</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Privacy & Security → Location Services</strong></li>
<li>Review each app's location access. Set most apps to <strong>"While Using"</strong> or <strong>"Never"</strong></li>
<li>Turn off <strong>"Precise Location"</strong> for apps that do not need exact coordinates (social media, news, shopping)</li>
<li>Under <strong>System Services</strong> (bottom of Location Services): disable "iPhone Analytics," "Routing & Traffic," "Improve Maps," and "Significant Locations"</li>
</ol>

<h3>3. App Privacy Audit</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Privacy & Security → App Privacy Report</strong></li>
<li>Enable it. After a week, review which apps access your camera, microphone, contacts, and location — and how frequently</li>
<li>Remove access for apps that should not need specific permissions</li>
</ol>

<h3>4. Safari Privacy</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Safari</strong></li>
<li>Enable <strong>"Prevent Cross-Site Tracking"</strong></li>
<li>Enable <strong>"Hide IP Address"</strong> (from trackers, or from trackers and websites)</li>
<li>Set <strong>"Block All Cookies"</strong> if you can tolerate some sites breaking (or leave cross-site tracking prevention on)</li>
<li>Disable <strong>"Search Engine Suggestions"</strong> and <strong>"Safari Suggestions"</strong> to reduce data sent to Apple</li>
</ul>

<h3>5. Additional iOS Settings</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Settings → Privacy & Security → Analytics & Improvements:</strong> Turn off all options (Share iPhone Analytics, Improve Siri, etc.)</li>
<li><strong>Settings → Privacy & Security → Apple Advertising:</strong> Turn off "Personalized Ads"</li>
<li><strong>Settings → Mail → Privacy Protection:</strong> Enable "Protect Mail Activity" to block email tracking pixels</li>
<li><strong>Settings → Phone → Silence Unknown Callers:</strong> Enable to block spam calls</li>
<li><strong>Lock Screen:</strong> Disable Control Center, Notification Center, Siri, and Reply with Message from the lock screen (Settings → Face ID & Passcode)</li>
</ul>

<h2>Android Privacy Settings</h2>
<h3>1. Disable Ad Tracking</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Privacy → Ads</strong> (or Settings → Google → Ads)</li>
<li>Tap <strong>"Delete advertising ID"</strong> — this permanently removes your ad tracking ID. Apps can no longer use it for cross-app tracking.</li>
</ol>

<h3>2. App Permissions Audit</h3>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Privacy → Permission Manager</strong></li>
<li>Review each permission category: Camera, Microphone, Location, Contacts, Files, Phone, SMS</li>
<li>For each app, choose: <strong>"Allow only while using the app," "Ask every time,"</strong> or <strong>"Don't allow"</strong></li>
<li>Pay special attention to <strong>Camera and Microphone</strong> — apps should not have background access to these</li>
<li>Check <strong>"Nearby Devices"</strong> permission — used for Bluetooth tracking</li>
</ol>

<h3>3. Location Settings</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Go to <strong>Settings → Location</strong></li>
<li>Tap <strong>"App location permissions"</strong> and set most apps to "While using" or "Denied"</li>
<li>Disable <strong>"Google Location History"</strong> and <strong>"Web & App Activity"</strong> in your Google Account settings (these are separate from device location permissions)</li>
<li>Go to <strong>myactivity.google.com</strong> and delete stored location data, search history, and YouTube history</li>
</ul>

<h3>4. Additional Android Settings</h3>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Settings → Privacy → Privacy Dashboard:</strong> View a timeline of which apps accessed sensitive permissions in the last 24 hours</li>
<li><strong>Settings → Privacy:</strong> Enable "Camera access" and "Microphone access" indicators (show a green dot when in use)</li>
<li><strong>Settings → Security:</strong> Enable "Google Play Protect" to scan for malicious apps</li>
<li><strong>Disable lock screen notifications</strong> or set to "Show sensitive content only when unlocked"</li>
<li><strong>Review connected apps:</strong> Go to myaccount.google.com → Security → Third-party apps with account access. Remove anything you do not use.</li>
</ul>

<h2>Universal Tips (Both Platforms)</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Use a VPN</strong> — especially on public WiFi. See our <a href="/guide/vpn-buying-guide" style="color:#0d9488">VPN guide</a>.</li>
<li><strong>Use encrypted messaging:</strong> Signal is the gold standard. iMessage is good for Apple-to-Apple communication.</li>
<li><strong>Update your phone:</strong> Security patches fix vulnerabilities that attackers exploit. Enable automatic updates.</li>
<li><strong>Review app permissions after updates:</strong> Some apps request new permissions after updates. Do not auto-approve.</li>
<li><strong>Uninstall unused apps:</strong> Every installed app is a potential data collector, even if you never open it.</li>
</ul>

<p style="font-size:14px;color:#374151;line-height:1.8">See also: <a href="/guide/stop-being-tracked-online" style="color:#0d9488">Stop Being Tracked Online</a> · <a href="/guide/private-browsing-guide" style="color:#0d9488">Private Browsing Guide</a>.</p>
"""},

    "private-browsing-guide": {
        "title": f"Private Browsing Guide — What It Does (and Doesn't) Do {YEAR}",
        "desc": f"What private browsing actually does and doesn't do. Incognito misconceptions, Tor, VPNs, private search engines. Updated {MY}.",
        "content": f"""
<h1>Private Browsing Guide — What It Does (and Doesn't) Do {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Most people think incognito mode makes them invisible online. It does not. This guide explains what private browsing actually protects against, what it does not, and what tools you need for real privacy. Updated {MY}.</p>

<h2>What Incognito Mode Actually Does</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">When you open a private/incognito window, the browser creates a temporary session that is deleted when you close it. Specifically:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Browsing history is not saved</strong> — sites you visit will not appear in your history</li>
<li><strong>Cookies are deleted</strong> when you close the window — you will be logged out of everything</li>
<li><strong>Form data is not saved</strong> — autofill information is not stored</li>
<li><strong>Search history is not saved</strong> locally (but may still be saved by the search engine)</li>
<li><strong>Downloaded files remain</strong> on your device — only the download history is cleared</li>
</ul>

<h2>What Incognito Mode Does NOT Do</h2>
<p style="font-size:14px;color:#374151;line-height:1.8"><strong>This is critical.</strong> Most people overestimate what private browsing protects against:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Your ISP can still see every site you visit.</strong> Private browsing does not encrypt your traffic or hide your DNS requests. Your Internet Service Provider has a complete log of your browsing.</li>
<li><strong>Your employer/school can still see your traffic</strong> if you are on their network or using their device. Network monitoring tools see all traffic regardless of browser mode.</li>
<li><strong>Websites can still see your IP address.</strong> Every site you visit knows your IP address, approximate location, and ISP.</li>
<li><strong>Websites can still fingerprint your browser.</strong> Your browser fingerprint (screen size, fonts, timezone, etc.) is the same in incognito mode.</li>
<li><strong>Google still logs your searches</strong> if you are signed into Google (or even if you are not — they track by IP and fingerprint).</li>
<li><strong>Downloaded files stay on your computer.</strong> Bookmarks created in incognito are also saved permanently.</li>
<li><strong>Extensions may still track you</strong> if they are enabled in incognito mode.</li>
</ul>

<h2>When Private Browsing IS Useful</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Shared computers:</strong> Prevents the next person from seeing your browsing history and logged-in accounts</li>
<li><strong>Price comparison:</strong> Some travel and shopping sites show higher prices to returning visitors (using cookies). Incognito avoids this.</li>
<li><strong>Testing:</strong> Web developers use incognito to test sites without cached data</li>
<li><strong>Logging into multiple accounts:</strong> Open a second session on the same site with a different account</li>
</ul>

<h2>Tools for Real Privacy</h2>
<h3>1. Tor Browser — True Anonymity</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Tor routes your traffic through three encrypted relays around the world. The website sees the exit relay's IP address, not yours. Your ISP sees you connected to Tor but cannot see what you are doing. <strong>Limitations:</strong> Tor is slow (multiple relay hops), some sites block Tor exit nodes, and it does not protect against browser exploits. Use it for situations requiring true anonymity, not for everyday browsing.</p>

<h3>2. VPN — Hide Your IP and Encrypt Traffic</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">A VPN encrypts all your internet traffic and hides your real IP address from websites. Unlike Tor, a VPN is fast enough for everyday use (streaming, downloads). However, you are trusting the VPN provider with your traffic instead of your ISP. Choose a trustworthy provider — see our <a href="/guide/vpn-buying-guide" style="color:#0d9488">VPN buying guide</a>.</p>

<h3>3. Private Search Engines</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">Even in incognito mode, Google tracks your searches. Switch to a private search engine:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>DuckDuckGo:</strong> No search history stored, no user tracking, no filter bubble. Uses its own index plus Bing results. Good for most searches.</li>
<li><strong>Startpage:</strong> Google search results without Google tracking. Proxy feature lets you visit search results through Startpage's servers.</li>
<li><strong>Brave Search:</strong> Independent search index (not sourced from Google or Bing). No tracking. Growing quickly in quality.</li>
<li><strong>SearXNG:</strong> Open source, self-hostable meta search engine. Aggregates results from multiple engines without tracking.</li>
</ul>

<h3>4. Privacy-Focused Browsers</h3>
<p style="font-size:14px;color:#374151;line-height:1.8">For everyday browsing with better privacy than Chrome's incognito mode:</p>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Brave:</strong> Blocks ads and trackers by default. Fingerprinting protection. Built-in Tor windows. Best all-around privacy browser for daily use.</li>
<li><strong>Firefox:</strong> Enhanced Tracking Protection. Container tabs to isolate sites. Highly configurable. Backed by non-profit Mozilla.</li>
<li><strong>LibreWolf:</strong> Firefox fork with privacy-focused defaults. Telemetry removed. For advanced users.</li>
</ul>

<h2>The Privacy Spectrum</h2>
<p style="font-size:14px;color:#374151;line-height:1.8">Here is a practical overview from least to most private:</p>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li><strong>Chrome normal mode:</strong> Minimal privacy. Google collects extensive data.</li>
<li><strong>Chrome incognito:</strong> Hides history from other users on the same device. Nothing more.</li>
<li><strong>Firefox/Brave with tracker blocking:</strong> Blocks most third-party tracking. Good daily driver.</li>
<li><strong>Firefox/Brave + VPN:</strong> Hides your IP from websites and your browsing from your ISP.</li>
<li><strong>Firefox/Brave + VPN + encrypted DNS:</strong> Prevents DNS-level tracking.</li>
<li><strong>Tor Browser:</strong> Maximum anonymity for specific tasks. Too slow for daily use.</li>
<li><strong>Tor + Tails OS (on USB):</strong> Maximum possible anonymity. Leaves no trace on the computer.</li>
</ol>

<p style="font-size:14px;color:#374151;line-height:1.8">For most people, step 4 (privacy browser + VPN) provides excellent protection without sacrificing usability. See also: <a href="/guide/stop-being-tracked-online" style="color:#0d9488">Stop Being Tracked Online</a> · <a href="/guide/most-private-phone-settings" style="color:#0d9488">Private Phone Settings</a>.</p>
"""},
}


def mount_guide_pages(app):
    """Mount all curated guide pages."""

    # Dynamic guide route
    @app.get("/guide/{slug}", response_class=HTMLResponse)
    async def guide_page(slug: str):
        guide = GUIDES.get(slug)
        if not guide:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        ck = f"guide:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        faq_items = [
            (guide["title"].replace(f" — {YEAR} Guide", "").replace(f" {YEAR}", "") + "?",
             guide["desc"][:200]),
        ]
        faq_html = "".join(f'<div style="font-weight:600;padding:12px 0;border-bottom:1px solid #e5e7eb">{q}</div><div style="font-size:13px;color:#374151;padding:8px 0 12px">{a}</div>' for q, a in faq_items)
        faq_ld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}' for q, a in faq_items)

        page = _head(guide["title"][:60] + " | Nerq", guide["desc"][:160],
                     f"{SITE}/guide/{slug}",
                     f'<meta name="nerq:type" content="guide"><meta name="nerq:updated" content="{TODAY}">'
                     f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_ld}]}}</script>')
        page += guide["content"]
        page += f"""
<h2>Related Guides</h2>
<div style="display:flex;flex-wrap:wrap;gap:6px;font-size:12px">
{"".join(f'<a href="/guide/{s}" style="color:#0d9488;padding:4px 8px;border:1px solid #e5e7eb">{g["title"][:40]}</a>' for s, g in list(GUIDES.items())[:8] if s != slug)}
</div>
<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/trending" style="color:#0d9488">Trending</a> · <a href="/leaderboard" style="color:#0d9488">Leaderboard</a> ·
<a href="/discover" style="color:#0d9488">Discover</a> · <a href="/best/safest-apps-2026" style="color:#0d9488">Safest Apps</a>
</div>"""
        page += _foot()
        return HTMLResponse(_sc(ck, page))

    # /check-website landing page
    @app.get("/check-website", response_class=HTMLResponse)
    async def check_website():
        page = _head(f"Is This Website Safe? — URL Trust Checker {YEAR} | Nerq",
                     f"Check any website for scam indicators, trust score, and safety analysis. Free. Updated {MY}.",
                     f"{SITE}/check-website",
                     f'<meta name="nerq:type" content="tool"><meta name="nerq:updated" content="{TODAY}">')
        page += f"""
<h1>Is This Website Safe?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Check any URL for scam indicators, trust score, and safety analysis. We analyze domain age, SSL, ownership, and 15+ safety signals.</p>
<div style="max-width:500px;margin:20px auto;display:flex;gap:8px">
<input type="text" id="url-input" placeholder="Enter any URL: amazon.com, suspicious-shop.xyz..."
  style="flex:1;padding:12px 16px;border:1px solid #e5e7eb;font-size:16px;font-family:system-ui">
<button onclick="var q=document.getElementById('url-input').value.trim().replace(/https?:\\/\\//,'').replace(/\\/.*/,'').replace(/^www\\./,'');if(q)window.location='/is-'+q.replace(/\\./g,'-')+'-safe'"
  style="padding:12px 24px;background:#0d9488;color:white;border:none;font-weight:600;cursor:pointer;font-size:15px">CHECK</button>
</div>
<p style="text-align:center;font-size:13px;color:#6b7280;margin-top:12px">Free. No signup. Instant results.</p>

<h2>What We Check</h2>
<table>
<tr><td>Domain Age</td><td>Older domains are more trustworthy</td></tr>
<tr><td>SSL Certificate</td><td>Valid HTTPS with reputable issuer</td></tr>
<tr><td>Owner Transparency</td><td>Is the owner identifiable?</td></tr>
<tr><td>User Reports</td><td>Known scam or fraud reports</td></tr>
<tr><td>Content Quality</td><td>Professional vs suspicious content</td></tr>
<tr><td>Payment Safety</td><td>Accepts credit cards with buyer protection?</td></tr>
</table>

<h2>Popular Checks</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px;font-size:13px">
<a href="/is-temu-safe-to-buy-from" style="color:#0d9488">Is Temu Safe?</a>
<a href="/is-shein-safe-to-buy-from" style="color:#0d9488">Is Shein Safe?</a>
<a href="/is-aliexpress-safe-to-buy-from" style="color:#0d9488">Is AliExpress Safe?</a>
<a href="/is-amazon-safe-to-buy-from" style="color:#0d9488">Is Amazon Safe?</a>
<a href="/is-ebay-safe-to-buy-from" style="color:#0d9488">Is eBay Safe?</a>
</div>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/guide/how-to-spot-fake-website" style="color:#0d9488">How to Spot Fake Websites</a> ·
<a href="/guide/online-shopping-safety" style="color:#0d9488">Shopping Safety</a> ·
<a href="/best/safest-shopping-sites" style="color:#0d9488">Safest Shopping Sites</a>
</div>"""
        page += _foot()
        return HTMLResponse(page)

    # /guides hub page — all guides organized by category
    @app.get("/guides", response_class=HTMLResponse)
    async def guides_hub():
        ck = "guides:hub"
        c = _c(ck)
        if c: return HTMLResponse(c)

        categories = {
            "Consumer Safety": ["how-to-spot-fake-website", "online-shopping-safety", "best-free-antivirus", "is-exe-safe", "wordpress-security-guide", "safe-browser-extensions"],
            "Kids & Family": ["internet-safety-for-kids", "safe-games-for-kids", "parental-controls-guide", "safe-apps-for-children"],
            "Security": ["what-to-do-if-hacked", "password-safety", "two-factor-authentication", "how-to-check-for-data-breach"],
            "Privacy": ["vpn-buying-guide", "stop-being-tracked-online", "most-private-phone-settings", "private-browsing-guide"],
        }

        page = _head(f"Safety & Security Guides {YEAR} | Nerq",
                      f"Free safety and security guides. VPN, passwords, kids' safety, privacy, and more. Independent, no affiliate links. Updated {MY}.",
                      f"{SITE}/guides",
                      f'<meta name="nerq:type" content="hub"><meta name="nerq:updated" content="{TODAY}">')
        page += f"""<h1>Safety & Security Guides {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Free, independent guides — no affiliate links, no ads. Updated {MY}.</p>"""

        for cat_name, slugs in categories.items():
            page += f'<h2>{cat_name}</h2>\n<ul style="font-size:14px;color:#374151;line-height:2">\n'
            for slug in slugs:
                guide = GUIDES.get(slug)
                if guide:
                    page += f'<li><a href="/guide/{slug}" style="color:#0d9488;font-weight:600">{guide["title"]}</a><br><span style="font-size:13px;color:#6b7280">{guide["desc"][:120]}</span></li>\n'
            page += '</ul>\n'

        page += f"""
<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/check-website" style="color:#0d9488">Website Trust Checker</a> ·
<a href="/trending" style="color:#0d9488">Trending</a> ·
<a href="/leaderboard" style="color:#0d9488">Leaderboard</a> ·
<a href="/discover" style="color:#0d9488">Discover</a>
</div>"""
        page += _foot()
        return HTMLResponse(_sc(ck, page))

    # Guide sitemap
    @app.get("/sitemap-guides-curated.xml", response_class=Response)
    async def sitemap_guides():
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        xml += f'<url><loc>{SITE}/guides</loc><lastmod>{TODAY}</lastmod><priority>0.9</priority></url>\n'
        xml += f'<url><loc>{SITE}/check-website</loc><lastmod>{TODAY}</lastmod><priority>0.9</priority></url>\n'
        for slug in GUIDES:
            xml += f'<url><loc>{SITE}/guide/{slug}</loc><lastmod>{TODAY}</lastmod><priority>0.8</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    logger.info(f"Mounted {len(GUIDES)} guide pages + /check-website + sitemap")
