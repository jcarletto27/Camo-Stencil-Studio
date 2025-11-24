#!/bin/bash

if [ ! -d "venv" ]; then
    echo "[!] Virtual environment not found! Please run ./setup_linux.sh first."
        exit 1
        fi

        source venv/bin/activate
        python3 camo_studio.py
