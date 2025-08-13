#!/bin/bash
# Detect package manager
if command -v dnf &>/dev/null; then
    PM=dnf
else
    PM=yum
fi

show_usage() {
    echo "Usage: $0 [--security | --non-security | --all]"
    exit 1
}

if [ $# -ne 1 ]; then
    show_usage
fi

# Extract package names from security updates correctly
SECURITY_PKGS=$($PM updateinfo list security all -q | awk '{print $3}' | sort -u)

mode=$1

case $mode in
    --security)
        echo -e "Package\tCurrent_Version\tAvailable_Version\tType"
        echo "-------------------------------------------------------------"
        echo "$SECURITY_PKGS" | while read pkg; do
            avail=$($PM list updates "$pkg" -q 2>/dev/null | awk 'NR>1 {print $2}')
            current=$($PM list installed "$pkg" -q 2>/dev/null | awk 'NR>1 {print $2}')
            if [ -n "$avail" ]; then
                echo -e "${pkg}\t${current}\t${avail}\tSecurity"
            fi
        done
        ;;
        
    --non-security)
        all_updates=$(mktemp)
        security_updates=$(mktemp)

        $PM list updates -q | awk 'NR>1 {print $1, $2}' | sort > "$all_updates"
        echo "$SECURITY_PKGS" > "$security_updates"
        
        echo -e "Package\tCurrent_Version\tAvailable_Version\tType"
        echo "-------------------------------------------------------------"
        grep -F -v -f "$security_updates" "$all_updates" | while read pkg avail; do
            current=$($PM list installed "$pkg" -q 2>/dev/null | awk 'NR>1 {print $2}')
            echo -e "${pkg}\t${current}\t${avail}\tNon-Security"
        done
        
        rm -f "$all_updates" "$security_updates"
        ;;
        
    --all)
        echo -e "Package\tCurrent_Version\tAvailable_Version\tType"
        echo "-------------------------------------------------------------"
        $PM list updates -q | awk 'NR>1 {print $1, $2}' | while read pkg avail; do
            current=$($PM list installed "$pkg" -q 2>/dev/null | awk 'NR>1 {print $2}')
            if echo "$SECURITY_PKGS" | grep -Fxq "$pkg"; then
                type="Security"
            else
                type="Non-Security"
            fi
            echo -e "${pkg}\t${current}\t${avail}\t${type}"
        done
        ;;
        
    *)
        show_usage
        ;;
esac
