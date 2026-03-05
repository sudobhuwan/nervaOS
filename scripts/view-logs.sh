#!/usr/bin/env bash
# NervaOS Log Viewer - Real-time system logs

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Pre-flight checks
check_daemon_status() {
    if systemctl --user is-active --quiet nerva-service; then
        echo -e "${GREEN}✓ NervaOS daemon is running${NC}"
        return 0
    else
        echo -e "${RED}✗ NervaOS daemon is not running${NC}"
        echo -e "${YELLOW}  Start it with: systemctl --user start nerva-service${NC}"
        return 1
    fi
}

check_journal_access() {
    if ! journalctl --user -u nerva-service --since "1 minute ago" &>/dev/null; then
        echo -e "${RED}✗ Cannot access journalctl logs${NC}"
        echo -e "${YELLOW}  Check permissions or journald service${NC}"
        return 1
    else
        echo -e "${GREEN}✓ Journal access OK${NC}"
        return 0
    fi
}

check_dependencies() {
    missing_deps=()
    
    if ! command -v journalctl &> /dev/null; then
        missing_deps+=("systemd (for journalctl)")
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠ Missing dependencies: ${missing_deps[*]}${NC}"
        return 1
    else
        echo -e "${GREEN}✓ All dependencies available${NC}"
        return 0
    fi
}

show_system_status() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}System Status:${NC}"
    
    # Daemon status
    if systemctl --user is-active --quiet nerva-service; then
        status=$(systemctl --user show nerva-service --property=ActiveState --value)
        echo -e "  Daemon: ${GREEN}${status}${NC}"
    else
        echo -e "  Daemon: ${RED}not running${NC}"
    fi
    
    # Recent log count
    log_count=$(journalctl --user -u nerva-service --since "1 hour ago" --no-pager | wc -l)
    echo -e "  Recent logs (1h): ${BLUE}${log_count} lines${NC}"
    
    # Last activity
    last_log=$(journalctl --user -u nerva-service -n 1 --no-pager --format="%s" 2>/dev/null | head -c 60)
    if [ -n "$last_log" ]; then
        echo -e "  Last activity: ${YELLOW}${last_log}...${NC}"
    fi
    
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Run pre-flight checks
run_preflight() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║          NervaOS Real-time Log Viewer                     ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}Running pre-flight checks...${NC}"
    echo ""
    
    all_ok=true
    
    check_dependencies || all_ok=false
    check_journal_access || all_ok=false
    check_daemon_status || all_ok=false
    
    echo ""
    
    if [ "$all_ok" = false ]; then
        echo -e "${YELLOW}⚠ Some checks failed, but continuing anyway...${NC}"
        echo ""
    fi
    
    show_system_status
}

# Function to show all NervaOS logs
show_all_logs() {
    echo -e "${GREEN}Showing all NervaOS logs (daemon + UI)...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    # Combine daemon service logs with UI logs
    journalctl --user -f \
        -u nerva-service \
        _COMM=nerva-ui \
        _COMM=nerva-daemon \
        + _COMM=python | grep -i nerva
}

# Function to show daemon logs only
show_daemon_logs() {
    echo -e "${GREEN}Showing NervaOS daemon logs...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -u nerva-service -f
}

# Function to show UI logs only
show_ui_logs() {
    echo -e "${GREEN}Showing NervaOS UI logs...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -f _COMM=nerva-ui
}

# Function to show logs with full details
show_verbose_logs() {
    echo -e "${GREEN}Showing verbose logs with all details...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -f \
        -u nerva-service \
        --full \
        --no-pager \
        -o verbose
}

# Function to show logs by component
show_component_logs() {
    component=$1
    echo -e "${GREEN}Showing ${component} logs...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -f \
        -u nerva-service \
        | grep -i "nerva-${component}"
}

# Function to show logs from last N minutes
show_recent_logs() {
    minutes=${1:-10}
    echo -e "${GREEN}Showing logs from last ${minutes} minutes, then following...${NC}"
    echo ""
    
    journalctl --user \
        -u nerva-service \
        --since "${minutes} minutes ago" \
        -f
}

# Function to show error logs only
show_error_logs() {
    echo -e "${RED}Showing ERROR and WARNING logs only...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -f \
        -u nerva-service \
        -p err..warning
}

# Function to show system-wide logs
show_system_logs() {
    echo -e "${GREEN}Showing system-wide NervaOS logs...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    sudo journalctl -f | grep -i nerva
}

# Function to show all logs with colored output
show_colored_logs() {
    echo -e "${GREEN}Showing all logs with color coding...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""
    
    journalctl --user -f \
        -u nerva-service \
        | sed -E \
            -e "s/(ERROR|ERRORS)/${RED}\1${NC}/g" \
            -e "s/(WARNING|WARN)/${YELLOW}\1${NC}/g" \
            -e "s/(INFO)/${GREEN}\1${NC}/g" \
            -e "s/(DEBUG)/${BLUE}\1${NC}/g"
}

# Main menu
if [ $# -eq 0 ]; then
    # Run pre-flight checks first
    run_preflight
    
    echo "Usage: $0 [option]"
    echo ""
    echo "Options:"
    echo "  all              - Show all NervaOS logs (daemon + UI)"
    echo "  daemon           - Show daemon service logs only"
    echo "  ui               - Show UI application logs only"
    echo "  verbose          - Show verbose logs with full details"
    echo "  errors           - Show only ERROR and WARNING logs"
    echo "  recent [N]       - Show logs from last N minutes (default: 10)"
    echo "  component NAME   - Show logs for specific component (e.g., voice, automation)"
    echo "  system           - Show system-wide logs (requires sudo)"
    echo "  colored          - Show logs with color coding"
    echo "  status           - Show system status only (no logs)"
    echo ""
    echo "Examples:"
    echo "  $0 all                    # All logs"
    echo "  $0 daemon                 # Daemon only"
    echo "  $0 errors                 # Errors only"
    echo "  $0 recent 5               # Last 5 minutes"
    echo "  $0 component voice        # Voice component only"
    echo ""
    
    # Default to showing all logs
    show_all_logs
else
    case "$1" in
        status)
            run_preflight
            exit 0
            ;;
        all)
            run_preflight
            show_all_logs
            ;;
        daemon)
            run_preflight
            show_daemon_logs
            ;;
        ui)
            run_preflight
            show_ui_logs
            ;;
        verbose)
            run_preflight
            show_verbose_logs
            ;;
        errors)
            run_preflight
            show_error_logs
            ;;
        recent)
            run_preflight
            show_recent_logs "${2:-10}"
            ;;
        component)
            if [ -z "$2" ]; then
                echo -e "${RED}Error: Component name required${NC}"
                echo "Usage: $0 component [voice|automation|ai|context|etc]"
                exit 1
            fi
            run_preflight
            show_component_logs "$2"
            ;;
        system)
            run_preflight
            show_system_logs
            ;;
        colored)
            run_preflight
            show_colored_logs
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Run '$0' without arguments to see usage"
            exit 1
            ;;
    esac
fi
