#!/bin/bash
#
# universal_update_checker.sh
# Works for: Amazon Linux 1/2/2023, RHEL/CentOS/Rocky/Alma
# Shows: Package | Current_Version | Available_Version | Type
# Optional filters: --sec or --non-sec
#

FILTER="$1"

# ─────────────────────────────────────────────
# Detect OS & Package Manager
# ─────────────────────────────────────────────
if grep -qi "Amazon Linux" /etc/os-release; then
    if command -v dnf &>/dev/null; then
        OS="Amazon Linux"
        PM=dnf
    else
        OS="Amazon Linux"
        PM=yum
    fi
elif grep -Eqi "Red Hat|CentOS|Rocky|Alma" /etc/os-release; then
    if command -v dnf &>/dev/null; then
        OS="RHEL"
        PM=dnf
    else
        OS="RHEL"
        PM=yum
    fi
else
    echo "❌ Unsupported OS. This script supports Amazon Linux & RHEL-like systems only."
    exit 1
fi

# ─────────────────────────────────────────────
# Get Security Updates List
# ─────────────────────────────────────────────
if [ "$PM" = "dnf" ]; then
    SECURITY_PKGS=$($PM updateinfo list security all 2>/dev/null | awk 'NR>2 {print $3}' | sort -u)
else
    if ! yum -q list installed yum-plugin-security &>/dev/null; then
        echo "ℹ️ Installing yum-plugin-security..."
        yum install -y yum-plugin-security &>/dev/null
    fi
    SECURITY_PKGS=$(yum updateinfo list security all 2>/dev/null | awk 'NR>2 {print $3}' | sort -u)
fi

# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
printf "%-35s %-25s %-25s %-15s\n" "Package" "Current_Version" "Available_Version" "Type"
printf "%-35s %-25s %-25s %-15s\n" "-------" "---------------" "----------------" "----"

# ─────────────────────────────────────────────
# Process Updates Function
# ─────────────────────────────────────────────
process_updates() {
    local pkg latest basepkg current type
    while read -r pkg latest; do
        basepkg=$(echo "$pkg" | cut -d. -f1)
        current=$(rpm -q --qf "%{VERSION}-%{RELEASE}\n" "$basepkg" 2>/dev/null)

        if echo "$SECURITY_PKGS" | grep -qw "$pkg"; then
            type="Security"
        else
            type="Non-Security"
        fi

        # Apply filter
        case "$FILTER" in
            --sec)
                [[ "$type" != "Security" ]] && continue
                ;;
            --non-sec)
                [[ "$type" != "Non-Security" ]] && continue
                ;;
        esac

        printf "%-35s %-25s %-25s %-15s\n" "$pkg" "$current" "$latest" "$type"
    done
}

# ─────────────────────────────────────────────
# Fetch Updates & Process
# ─────────────────────────────────────────────
if [ "$PM" = "dnf" ]; then
    $PM list updates --refresh 2>/dev/null | awk 'NR>2 {print $1,$2}' | process_updates
else
    yum list updates 2>/dev/null | awk 'NR>2 {print $1,$2}' | process_updates
fi
