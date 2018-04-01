#!/bin/bash
# I am an Ansible old-style module.

INPUT=$1

[ ! -r "$INPUT" ] && {
    echo "Usage: $0 <input.json>" >&2
    exit 1
}

echo "{"
echo "  \"changed\": false,"
echo "  \"msg\": \"Here is my input\","
echo "  \"filname\": \"$INPUT\","
echo "  \"input\": [\"$(cat $INPUT | tr \" \' )\"]"
echo "}"
