#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/env python3 "$DIR/main.py" "$@"
