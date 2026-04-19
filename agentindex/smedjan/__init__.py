"""In-tree helpers used by agentindex render code.

Kept separate from the top-level `smedjan` package (factory/worker code) so
that `agentindex.*` modules do not pull in factory writers just to render a
page. Imports should stay narrow: `from agentindex.smedjan.l2_block_2a
import render_external_trust_block` and nothing transitive.
"""
