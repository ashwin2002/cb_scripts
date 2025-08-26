#!/bin/bash

# Keywords to match (case-insensitive regex)
keywords="unstable|inst_fail|pending|failure|aborted"

# Temporary file to hold results
tmpfile=$(mktemp)

# Read from input (file or stdin)
while IFS= read -r line; do
    # Lowercase version of line for matching
    lower_line=$(echo "$line" | tr '[:upper:]' '[:lower:]')

    # Check if line contains any of the keywords
    if echo "$lower_line" | grep -Eq "$keywords"; then
        # Get first word
        first_word=$(echo "$line" | awk '{print $1}')

        # Extract component from prefix between 'debian-' and first '_'
        prefix="${first_word%%_*}"           # debian-collections
        component="${prefix#debian-}"        # collections

        # Extract test name after first '_'
        test_name="${first_word#*_}"         # rebalance_with_...

        # Output to temp file: component,test_name
        echo "$component,$test_name" >> "$tmpfile"
    fi
done < "${1:-/dev/stdin}"

# Now group and print
# Extract unique components
components=$(cut -d',' -f1 "$tmpfile" | sort | uniq)

for comp in $components; do
    echo "$comp"
    # Collect all test names for this component
    grep "^$comp," "$tmpfile" | cut -d',' -f2 | paste -sd "," -
    echo
done

# Clean up
rm "$tmpfile"

