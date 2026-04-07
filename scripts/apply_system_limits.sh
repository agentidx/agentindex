#!/bin/bash
# P0 Fix 1: System limits — run with sudo
# Usage: sudo bash ~/agentindex/scripts/apply_system_limits.sh

set -e

echo "=== Applying system limits ==="

# Immediate
sysctl -w kern.ipc.somaxconn=1024
sysctl -w net.inet.tcp.msl=5000
echo "Applied: somaxconn=1024, tcp.msl=5000"

# Persistent sysctl
cat > /etc/sysctl.conf << 'SYSCTL'
kern.ipc.somaxconn=1024
net.inet.tcp.msl=5000
SYSCTL
echo "Written /etc/sysctl.conf"

# maxfiles LaunchDaemon
cat > /Library/LaunchDaemons/limit.maxfiles.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>limit.maxfiles</string>
    <key>ProgramArguments</key>
    <array>
        <string>launchctl</string>
        <string>limit</string>
        <string>maxfiles</string>
        <string>65536</string>
        <string>200000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
PLIST
launchctl load /Library/LaunchDaemons/limit.maxfiles.plist 2>/dev/null || true
echo "Written + loaded limit.maxfiles LaunchDaemon"

# Auto-login (Fix 6)
defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser "anstudio"
echo "Set auto-login to anstudio"

echo ""
echo "=== Verification ==="
echo "somaxconn: $(sysctl -n kern.ipc.somaxconn)"
echo "tcp.msl: $(sysctl -n net.inet.tcp.msl)"
echo "maxfiles: $(launchctl limit maxfiles)"
echo "auto-login: $(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null)"
echo ""
echo "All P0 system-level fixes applied. Reload API LaunchAgent:"
echo "  launchctl unload ~/Library/LaunchAgents/com.nerq.api.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.nerq.api.plist"
