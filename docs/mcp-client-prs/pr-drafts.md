# MCP Client Integration PR Drafts

Upstream PRs to integrate Nerq trust scores into popular MCP clients.
Each draft targets a specific client and can be adapted into an actual PR
once the target repo's contribution guidelines are reviewed.

API reference: `GET https://nerq.ai/v1/preflight?target={name}`

Example response (trimmed):

```json
{
  "target": "filesystem-mcp-server",
  "target_trust": 82.3,
  "target_grade": "A",
  "target_verified": true,
  "target_category": "mcp-server",
  "interaction_risk": "LOW",
  "recommendation": "PROCEED",
  "security": {
    "known_cves": 0,
    "max_severity": null,
    "has_active_advisory": false,
    "license": "MIT",
    "license_category": "permissive"
  },
  "popularity": {
    "github_stars": 4200,
    "npm_weekly_downloads": 31000
  },
  "verified_by": "nerq.ai",
  "response_time_ms": 12.4
}
```

---

## 1. Continue.dev -- Trust score display in MCP server browser

**Title:** `feat: show Nerq trust scores when browsing MCP servers`

**Branch:** `feat/nerq-trust-badges`

**Target file(s):**
- `gui/src/components/mcpServers/McpServerCard.tsx`
- `gui/src/hooks/useMcpTrust.ts` (new)

### Description

When users browse available MCP servers in the Continue sidebar, there is no
trust signal to help them decide which servers are safe to install. This PR
adds a trust badge (grade + score) fetched from the Nerq preflight API. The
badge renders inline on each server card and links to the full report on
nerq.ai.

**Rationale:**
- MCP servers run arbitrary code with tool-call privileges. Users deserve a
  third-party trust signal before granting access.
- The Nerq API is zero-auth, cached for 1 hour, and responds in <50 ms.
  No API key is required.
- Scores are computed from GitHub activity, dependency health, CVE history,
  and community adoption -- not self-reported.

### Code diff

#### `gui/src/hooks/useMcpTrust.ts` (new file)

```typescript
import { useEffect, useState } from "react";

interface NerqPreflight {
  target_trust: number | null;
  target_grade: string | null;
  target_verified: boolean | null;
  interaction_risk: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  recommendation: "PROCEED" | "CAUTION" | "DENY" | "UNKNOWN";
  security: {
    known_cves: number;
    has_active_advisory: boolean;
    license: string | null;
  };
  details_url: string | null;
}

const CACHE = new Map<string, NerqPreflight>();

export function useMcpTrust(serverName: string | undefined) {
  const [trust, setTrust] = useState<NerqPreflight | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!serverName) return;

    const cached = CACHE.get(serverName);
    if (cached) {
      setTrust(cached);
      return;
    }

    setLoading(true);
    const url = `https://nerq.ai/v1/preflight?target=${encodeURIComponent(serverName)}`;

    fetch(url, { signal: AbortSignal.timeout(5000) })
      .then((r) => r.json())
      .then((data: NerqPreflight) => {
        CACHE.set(serverName, data);
        setTrust(data);
      })
      .catch(() => setTrust(null))
      .finally(() => setLoading(false));
  }, [serverName]);

  return { trust, loading };
}
```

#### `gui/src/components/mcpServers/McpServerCard.tsx` (diff)

```diff
 import { McpServer } from "../../types";
+import { useMcpTrust } from "../../hooks/useMcpTrust";
+
+const GRADE_COLORS: Record<string, string> = {
+  "A+": "#22c55e", A: "#22c55e", B: "#22c55e",
+  C: "#eab308", D: "#eab308",
+  E: "#ef4444", F: "#ef4444",
+};

 export function McpServerCard({ server }: { server: McpServer }) {
+  const { trust, loading } = useMcpTrust(server.name);
+
   return (
     <div className="mcp-server-card">
       <h3>{server.name}</h3>
+      {!loading && trust?.target_grade && (
+        <a
+          href={trust.details_url ?? `https://nerq.ai/safe/${server.name}`}
+          target="_blank"
+          rel="noopener noreferrer"
+          className="nerq-trust-badge"
+          title={`Trust Score: ${trust.target_trust}/100 | ${trust.interaction_risk} risk`}
+          style={{
+            display: "inline-flex",
+            alignItems: "center",
+            gap: "4px",
+            padding: "2px 8px",
+            borderRadius: "4px",
+            fontSize: "12px",
+            fontWeight: 600,
+            color: "#fff",
+            backgroundColor: GRADE_COLORS[trust.target_grade] ?? "#9ca3af",
+            textDecoration: "none",
+          }}
+        >
+          {trust.target_grade} &middot; {trust.target_trust}
+          {trust.security.known_cves > 0 && (
+            <span title={`${trust.security.known_cves} known CVEs`}>&#9888;</span>
+          )}
+        </a>
+      )}
       <p>{server.description}</p>
```

### API call example

```bash
curl -s 'https://nerq.ai/v1/preflight?target=filesystem-mcp-server' | jq '{
  target_trust, target_grade, recommendation, interaction_risk,
  cves: .security.known_cves, license: .security.license
}'
```

---

## 2. Cline -- Pre-connection trust gate for MCP servers

**Title:** `feat: warn before connecting to low-trust MCP servers`

**Branch:** `feat/nerq-trust-gate`

**Target file(s):**
- `src/core/mcp/McpHub.ts`
- `src/shared/mcp-trust.ts` (new)
- `src/core/config/settings.ts` (add setting)

### Description

Cline auto-connects to MCP servers listed in the config without any safety
check. This PR adds a pre-connection trust gate: before establishing a
connection to an MCP server, Cline calls the Nerq preflight API. If the
server scores below the configurable threshold (default: 40), the user sees
a warning dialog and must explicitly confirm.

**Rationale:**
- MCP servers can execute shell commands, read files, and make network
  requests. A compromised or poorly-maintained server is a supply-chain risk.
- The trust check adds ~15 ms latency on first connect (cached for 1 hour
  afterward). It never blocks high-trust servers.
- Users can disable the gate entirely or adjust the threshold in settings.

### Config integration

#### `src/core/config/settings.ts` (diff)

```diff
 export interface ClineSettings {
   // ...existing settings...
+  /**
+   * Nerq trust gate for MCP servers.
+   * - enabled: Whether to check trust scores before connecting (default: true)
+   * - threshold: Minimum trust score to auto-connect (default: 40)
+   * - blockUnknown: Block servers with no trust data (default: false)
+   */
+  mcpTrustGate?: {
+    enabled: boolean;
+    threshold: number;
+    blockUnknown: boolean;
+  };
 }
+
+export const DEFAULT_TRUST_GATE = {
+  enabled: true,
+  threshold: 40,
+  blockUnknown: false,
+};
```

### Code diff

#### `src/shared/mcp-trust.ts` (new file)

```typescript
import fetch from "node-fetch";

export interface TrustCheckResult {
  trust: number | null;
  grade: string | null;
  recommendation: "PROCEED" | "CAUTION" | "DENY" | "UNKNOWN";
  risk: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  cves: number;
  detailsUrl: string | null;
}

const cache = new Map<string, { result: TrustCheckResult; ts: number }>();
const CACHE_TTL_MS = 3600_000; // 1 hour

export async function checkMcpTrust(
  serverName: string
): Promise<TrustCheckResult> {
  const key = serverName.toLowerCase();
  const cached = cache.get(key);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return cached.result;
  }

  try {
    const url = `https://nerq.ai/v1/preflight?target=${encodeURIComponent(serverName)}`;
    const res = await fetch(url, { timeout: 5000 });
    const data = await res.json();

    const result: TrustCheckResult = {
      trust: data.target_trust,
      grade: data.target_grade,
      recommendation: data.recommendation,
      risk: data.interaction_risk,
      cves: data.security?.known_cves ?? 0,
      detailsUrl: data.details_url,
    };
    cache.set(key, { result, ts: Date.now() });
    return result;
  } catch {
    return {
      trust: null,
      grade: null,
      recommendation: "UNKNOWN",
      risk: "UNKNOWN",
      cves: 0,
      detailsUrl: null,
    };
  }
}
```

#### `src/core/mcp/McpHub.ts` (diff)

```diff
 import { McpServerConfig } from "../../shared/mcp";
+import { checkMcpTrust, TrustCheckResult } from "../../shared/mcp-trust";
+import { DEFAULT_TRUST_GATE } from "../config/settings";

 export class McpHub {
   // ...

   async connectToServer(config: McpServerConfig): Promise<void> {
+    const gate = this.settings.mcpTrustGate ?? DEFAULT_TRUST_GATE;
+
+    if (gate.enabled) {
+      const trust = await checkMcpTrust(config.name);
+
+      if (trust.recommendation === "DENY" ||
+          (trust.trust !== null && trust.trust < gate.threshold)) {
+        const proceed = await this.showTrustWarning(config.name, trust);
+        if (!proceed) {
+          this.log(`Blocked connection to ${config.name} (trust: ${trust.trust}, grade: ${trust.grade})`);
+          return;
+        }
+      }
+
+      if (trust.trust === null && gate.blockUnknown) {
+        const proceed = await this.showTrustWarning(config.name, trust);
+        if (!proceed) {
+          this.log(`Blocked unknown server ${config.name} (no trust data)`);
+          return;
+        }
+      }
+    }
+
     // ...existing connection logic...
   }

+  private async showTrustWarning(
+    serverName: string,
+    trust: TrustCheckResult
+  ): Promise<boolean> {
+    const score = trust.trust !== null ? `${trust.trust}/100` : "unknown";
+    const cveNote = trust.cves > 0 ? ` | ${trust.cves} known CVEs` : "";
+    const detailsLink = trust.detailsUrl ?? `https://nerq.ai/safe/${serverName}`;
+
+    const message = [
+      `MCP server "${serverName}" has a low trust score (${score}${cveNote}).`,
+      `Risk level: ${trust.risk}`,
+      `Full report: ${detailsLink}`,
+      "",
+      "Do you want to connect anyway?",
+    ].join("\n");
+
+    return this.ui.confirm("MCP Trust Warning", message);
+  }
 }
```

### API call example

```bash
# Pre-connection check -- called automatically before MCP handshake
curl -s 'https://nerq.ai/v1/preflight?target=sketchy-mcp-tool' | jq '{
  recommendation, interaction_risk, target_trust, target_grade,
  cves: .security.known_cves, advisory: .security.has_active_advisory
}'
```

Expected response for a low-trust server:

```json
{
  "recommendation": "DENY",
  "interaction_risk": "HIGH",
  "target_trust": 18.5,
  "target_grade": "F",
  "cves": 3,
  "advisory": true
}
```

---

## 3. Zed -- Trust score tooltips in MCP server panel

**Title:** `feat: add Nerq trust tooltips to MCP server panel`

**Branch:** `feat/nerq-mcp-trust-tooltips`

**Target file(s):**
- `crates/assistant/src/mcp/mcp_server_list.rs`
- `crates/assistant/src/mcp/nerq_trust.rs` (new)

### Description

The Zed MCP server panel lists configured servers by name with no trust
context. This PR adds a small trust indicator (colored dot + grade letter)
next to each server name. Hovering shows a tooltip with the full score,
risk level, CVE count, and a link to the Nerq report.

**Rationale:**
- Zed is positioning itself as an AI-native editor. MCP server trust is a
  natural extension of its security-conscious design.
- The indicator is non-intrusive: a 12px colored dot that only draws
  attention for CAUTION (amber) or DENY (red) servers.
- Data is fetched lazily on panel open and cached for the session.

### Code diff

#### `crates/assistant/src/mcp/nerq_trust.rs` (new file)

```rust
use anyhow::Result;
use collections::HashMap;
use gpui::SharedString;
use parking_lot::Mutex;
use serde::Deserialize;
use std::sync::Arc;
use std::time::{Duration, Instant};

const NERQ_API: &str = "https://nerq.ai/v1/preflight";
const CACHE_TTL: Duration = Duration::from_secs(3600);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Debug, Clone, Deserialize)]
pub struct NerqTrustData {
    pub target_trust: Option<f64>,
    pub target_grade: Option<String>,
    pub target_verified: Option<bool>,
    pub interaction_risk: String,
    pub recommendation: String,
    pub details_url: Option<String>,
    #[serde(default)]
    pub security: NerqSecurity,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct NerqSecurity {
    #[serde(default)]
    pub known_cves: u32,
    #[serde(default)]
    pub has_active_advisory: bool,
    pub license: Option<String>,
}

struct CacheEntry {
    data: NerqTrustData,
    fetched_at: Instant,
}

#[derive(Clone)]
pub struct NerqTrustCache {
    entries: Arc<Mutex<HashMap<String, CacheEntry>>>,
    client: reqwest::Client,
}

impl NerqTrustCache {
    pub fn new() -> Self {
        Self {
            entries: Arc::new(Mutex::new(HashMap::default())),
            client: reqwest::Client::builder()
                .timeout(REQUEST_TIMEOUT)
                .build()
                .expect("failed to build HTTP client"),
        }
    }

    pub async fn get_trust(&self, server_name: &str) -> Result<NerqTrustData> {
        let key = server_name.to_lowercase();

        // Check cache
        {
            let entries = self.entries.lock();
            if let Some(entry) = entries.get(&key) {
                if entry.fetched_at.elapsed() < CACHE_TTL {
                    return Ok(entry.data.clone());
                }
            }
        }

        // Fetch from API
        let url = format!(
            "{}?target={}",
            NERQ_API,
            urlencoding::encode(server_name)
        );
        let resp = self.client.get(&url).send().await?;
        let data: NerqTrustData = resp.json().await?;

        // Store in cache
        {
            let mut entries = self.entries.lock();
            entries.insert(key, CacheEntry {
                data: data.clone(),
                fetched_at: Instant::now(),
            });
        }

        Ok(data)
    }
}

impl NerqTrustData {
    /// Returns (dot_color_hex, label) for the UI indicator.
    pub fn indicator(&self) -> (&'static str, SharedString) {
        match self.recommendation.as_str() {
            "PROCEED" => (
                "#22c55e",
                SharedString::from(format!(
                    "{} {}",
                    self.target_grade.as_deref().unwrap_or("?"),
                    self.target_trust.map(|t| format!("{:.0}", t)).unwrap_or_default()
                )),
            ),
            "CAUTION" => (
                "#eab308",
                SharedString::from(format!(
                    "{} {}",
                    self.target_grade.as_deref().unwrap_or("?"),
                    self.target_trust.map(|t| format!("{:.0}", t)).unwrap_or_default()
                )),
            ),
            "DENY" => ("#ef4444", SharedString::from("Untrusted")),
            _ => ("#9ca3af", SharedString::from("Unknown")),
        }
    }

    /// Build tooltip text.
    pub fn tooltip(&self) -> String {
        let score = self
            .target_trust
            .map(|t| format!("{:.1}/100", t))
            .unwrap_or_else(|| "N/A".into());
        let grade = self.target_grade.as_deref().unwrap_or("?");
        let cve_line = if self.security.known_cves > 0 {
            format!("\nKnown CVEs: {}", self.security.known_cves)
        } else {
            String::new()
        };
        let link = self
            .details_url
            .as_deref()
            .unwrap_or("https://nerq.ai");

        format!(
            "Nerq Trust Score: {} (Grade {})\nRisk: {}\nRecommendation: {}{}\n\n{}",
            score,
            grade,
            self.interaction_risk,
            self.recommendation,
            cve_line,
            link,
        )
    }
}
```

#### `crates/assistant/src/mcp/mcp_server_list.rs` (diff)

```diff
 use super::mcp_server::McpServer;
+use super::nerq_trust::{NerqTrustCache, NerqTrustData};
+use collections::HashMap;

 pub struct McpServerListPanel {
     servers: Vec<McpServer>,
+    trust_cache: NerqTrustCache,
+    trust_data: HashMap<String, NerqTrustData>,
 }

 impl McpServerListPanel {
     pub fn new(cx: &mut ViewContext<Self>) -> Self {
         Self {
             servers: Vec::new(),
+            trust_cache: NerqTrustCache::new(),
+            trust_data: HashMap::default(),
         }
     }

+    fn fetch_trust_scores(&mut self, cx: &mut ViewContext<Self>) {
+        for server in &self.servers {
+            let name = server.name.clone();
+            let cache = self.trust_cache.clone();
+            cx.spawn(|this, mut cx| async move {
+                if let Ok(data) = cache.get_trust(&name).await {
+                    this.update(&mut cx, |this, cx| {
+                        this.trust_data.insert(name, data);
+                        cx.notify();
+                    })
+                    .ok();
+                }
+            })
+            .detach();
+        }
+    }

     fn render_server_row(
         &self,
         server: &McpServer,
         cx: &ViewContext<Self>,
     ) -> impl IntoElement {
+        let trust_indicator = self.trust_data.get(&server.name).map(|data| {
+            let (color, label) = data.indicator();
+            let tooltip_text = data.tooltip();
+
+            div()
+                .ml_2()
+                .flex()
+                .items_center()
+                .gap_1()
+                .child(
+                    div()
+                        .size(px(8.))
+                        .rounded_full()
+                        .bg(gpui::rgb(u32::from_str_radix(&color[1..], 16).unwrap_or(0x9ca3af)))
+                )
+                .child(
+                    div()
+                        .text_xs()
+                        .text_color(cx.theme().colors().text_muted)
+                        .child(label)
+                )
+                .tooltip(move |cx| Tooltip::text(tooltip_text.clone(), cx))
+        });
+
         h_flex()
             .gap_2()
             .child(Label::new(server.name.clone()))
+            .children(trust_indicator)
     }
 }
```

### API call example

```bash
# Fetched lazily when the MCP panel is opened
curl -s 'https://nerq.ai/v1/preflight?target=brave-search-mcp' | jq '{
  target_trust, target_grade, recommendation, interaction_risk,
  cves: .security.known_cves, license: .security.license,
  details_url
}'
```

---

## Notes for contributors

1. **No API key required.** The Nerq preflight endpoint is zero-auth with
   generous rate limits (60 req/min per IP). Responses include standard
   `Cache-Control: public, max-age=3600` and `ETag` headers.

2. **Graceful degradation.** All three integrations treat API failures as
   non-fatal. If Nerq is unreachable, the UI simply omits the trust badge.
   Connection to the MCP server is never blocked by a network error to Nerq.

3. **Privacy.** The only data sent to the Nerq API is the MCP server name
   (which is already public). No user data, tokens, or telemetry are
   transmitted.

4. **Trust methodology.** Scores are computed from: GitHub commit recency,
   star count, dependency vulnerability scans, CVE databases, license
   analysis, and community adoption metrics. Full methodology at
   https://nerq.ai/trust-score-methodology.
