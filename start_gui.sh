#!/bin/bash

echo ""
echo "========================================"
echo "  GitHub Follower Checker GUI"
echo "========================================"
echo ""

# Pruefe ob Python installiert ist
if ! command -v python3 &> /dev/null; then
    echo "FEHLER: Python3 ist nicht installiert!"
    echo "Bitte installiere Python3 über deinen Paketmanager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    echo "  Mac: brew install python3"
    echo ""
    read -p "Drücke Enter zum Beenden..."
    exit 1
fi

echo "Pruefe Dependencies..."

# Pruefe customtkinter
if ! python3 -c "import customtkinter" &> /dev/null; then
    echo ""
    echo "FEHLER: customtkinter ist nicht installiert!"
    echo ""
    echo "Installiere Dependencies..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "Installation fehlgeschlagen!"
        read -p "Drücke Enter zum Beenden..."
        exit 1
    fi
    echo ""
    echo "Installation erfolgreich!"
fi

# Pruefe requests
if ! python3 -c "import requests" &> /dev/null; then
    echo ""
    echo "FEHLER: requests ist nicht installiert!"
    echo "Installiere Dependencies..."
    pip3 install -r requirements.txt
fi

echo ""
echo "Starte GUI..."
echo ""

python3 GitHubFollowerCheckerGUI.py

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================"
    echo "  Fehler beim Starten der GUI!"
    echo "========================================"
    echo ""
    read -p "Drücke Enter zum Beenden..."
fi
