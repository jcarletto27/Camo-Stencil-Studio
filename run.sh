#!/bin/bash

# 0. Auto-Update Check
if command -v git &> /dev/null; then
    echo "[*] Checking for updates..."
#    git pull origin main
else
    echo "[!] Git not found. Skipping update check."
fi
echo ""

# 1. Run App
if [ ! -d "venv" ]; then
    echo "[!] Virtual environment not found! Please run ./setup_linux.sh first."
    exit 1
fi

source venv/bin/activate
python3 camo_studio.py
