#!/bin/bash

echo "========================================================"
echo "     CAMO STUDIO - LINUX SETUP WIZARD"
echo "========================================================"
echo ""

# 0. Check for Updates
echo "[*] Checking for Git..."
if command -v git &> /dev/null; then
    echo "[OK] Git found. Pulling latest updates..."
    git pull origin main
    if [ $? -ne 0 ]; then
        echo "[!] Git pull failed or not a git repository. Continuing with local version."
    else
        echo "[OK] Code updated."
    fi
else
    echo "[!] Git not found. Skipping update."
fi
echo ""

# 1. Check for Python 3
echo "[*] Checking for Python 3..."
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 could not be found."
    echo "    Please install Python 3 manually."
    exit 1
fi
echo "[OK] Python 3 found."
echo ""

# 2. Create Virtual Environment
if [ -d "venv" ]; then
    echo "[*] Virtual environment 'venv' already exists. Skipping creation."
else
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
    
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create virtual environment."
        echo "    (Note: On some distros like Ubuntu/Debian, you may need to manually"
        echo "     install the 'python3-venv' package using your package manager)."
        exit 1
    fi
    echo "[OK] Virtual environment created."
fi
echo ""

# 3. Activate and Install
echo "[*] Activating virtual environment..."
source venv/bin/activate

echo "[*] Upgrading pip..."
pip install --upgrade pip

echo ""
echo "[*] Installing required libraries..."
echo "    (opencv-python, numpy, svgwrite, Pillow, trimesh, shapely, scipy, mapbox_earcut)"
echo ""

pip install opencv-python numpy svgwrite Pillow trimesh shapely scipy mapbox_earcut

if [ $? -ne 0 ]; then
    echo ""
    echo "[!] There was an error installing dependencies."
    exit 1
fi

echo ""
echo "========================================================"
echo "[OK] SETUP COMPLETE!"
echo "========================================================"
echo ""
echo "You can now run the application using './run.sh'"
echo ""
