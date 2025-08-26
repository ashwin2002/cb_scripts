#!/bin/bash

# Keywords to match (case-insensitive regex)
keywords="unstable|inst_fail|pending|failure|aborted"

# Temporary file to hold results
tmpfile=$(mktemp)

# Read from input (file or stdin)
while IFS= read -r line; do
    lower_line=$(echo "$line" | tr '[:upper:]' '[:lower:]')
    if echo "$lower_line" | grep -Eq "$keywords"; then
        first_word=$(echo "$line" | awk '{print $1}')
        prefix="${first_word%%_*}"
        component="${prefix#debian-}"
        test_name="${first_word#*_}"
        echo "$component,$test_name" >> "$tmpfile"
    fi
done < "${1:-/dev/stdin}"

# Group and deduplicate
components=$(cut -d',' -f1 "$tmpfile" | sort | uniq)

for comp in $components; do
    echo "$comp"
    # Extract test names, sort, deduplicate, then join with commas
    grep "^$comp," "$tmpfile" \
        | cut -d',' -f2 \
        | sort -u \
        | paste -sd "," -
    echo
done

# Clean up
rm "$tmpfile"

