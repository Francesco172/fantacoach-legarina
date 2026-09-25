#!/bin/sh
cd "$(dirname "$0")"
( sleep 1; open "http://127.0.0.1:8787" ) >/dev/null 2>&1 &
python3 server.py
