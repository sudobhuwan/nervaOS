#!/usr/bin/env bash
# Check voice control dependencies

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Checking voice control dependencies..."
echo ""

missing=()
installed=()

# Check pyaudio
if python3 -c "import pyaudio" 2>/dev/null; then
    echo -e "${GREEN}✓ pyaudio${NC}"
    installed+=("pyaudio")
else
    echo -e "${RED}✗ pyaudio${NC}"
    missing+=("pyaudio")
fi

# Check deepgram-sdk
if python3 -c "from deepgram import Deepgram" 2>/dev/null; then
    echo -e "${GREEN}✓ deepgram-sdk${NC}"
    installed+=("deepgram-sdk")
else
    echo -e "${RED}✗ deepgram-sdk${NC}"
    missing+=("deepgram-sdk")
fi

# Check pyttsx3
if python3 -c "import pyttsx3" 2>/dev/null; then
    echo -e "${GREEN}✓ pyttsx3${NC}"
    installed+=("pyttsx3")
else
    echo -e "${RED}✗ pyttsx3${NC}"
    missing+=("pyttsx3")
fi

# Check pygame (voice mixer)
if python3 -c "import pygame" 2>/dev/null; then
    echo -e "${GREEN}✓ pygame${NC}"
    installed+=("pygame")
else
    echo -e "${RED}✗ pygame${NC}"
    missing+=("pygame")
fi

# Check websockets (Deepgram streaming)
if python3 -c "import websockets" 2>/dev/null; then
    echo -e "${GREEN}✓ websockets${NC}"
    installed+=("websockets")
else
    echo -e "${RED}✗ websockets${NC}"
    missing+=("websockets")
fi

echo ""

if [ ${#missing[@]} -eq 0 ]; then
    echo -e "${GREEN}All dependencies installed!${NC}"
    exit 0
else
    echo -e "${YELLOW}Missing dependencies: ${missing[*]}${NC}"
    echo ""
    read -p "Install missing dependencies? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        VENV_PATH="$HOME/.local/share/nervaos/venv"
        if [ -f "$VENV_PATH/bin/activate" ]; then
            source "$VENV_PATH/bin/activate"
            echo "Installing in virtual environment..."
            pip install "${missing[@]}"
        else
            echo "Installing globally..."
            pip3 install "${missing[@]}"
        fi
        echo -e "${GREEN}Installation complete!${NC}"
    else
        echo "Install manually with: pip install ${missing[*]}"
        exit 1
    fi
fi
