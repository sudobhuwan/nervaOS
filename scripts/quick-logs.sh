#!/usr/bin/env bash
# Quick log viewer - simplest command with checks

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Quick status check
echo -n "Checking daemon status... "
if systemctl --user is-active --quiet nerva-service; then
    echo -e "${GREEN}Running${NC}"
else
    echo -e "${RED}Not running${NC}"
    echo -e "${YELLOW}Start with: systemctl --user start nerva-service${NC}"
    exit 1
fi

echo ""
echo "Showing all NervaOS logs (Ctrl+C to stop)..."
echo ""

# All NervaOS logs in real-time
journalctl --user -f \
    -u nerva-service \
    + _COMM=nerva-ui \
    + _COMM=nerva-daemon \
    | grep -E "(nerva-|NERVA)" --color=always
