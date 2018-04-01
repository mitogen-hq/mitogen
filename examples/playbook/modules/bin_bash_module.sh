#!/bin/bash
exec >/tmp/derp
echo "$1"
cat "$1"

