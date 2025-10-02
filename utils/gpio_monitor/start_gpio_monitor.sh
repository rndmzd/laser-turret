#!/bin/bash
# Startup script for GPIO Monitor

echo "========================================="
echo "  Raspberry Pi 5 GPIO Monitor"
echo "========================================="
echo ""

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if running on Raspberry Pi
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model)
    echo "Detected: $MODEL"
else
    echo "Warning: Not running on Raspberry Pi"
fi

echo ""

# Check if virtual environment exists
if [ -d "$DIR/venv" ]; then
    echo "Activating virtual environment..."
    source "$DIR/venv/bin/activate"
else
    echo "No virtual environment found. Using system Python."
fi

# Check dependencies
echo "Checking dependencies..."
python3 -c "import flask, flask_socketio, gpiod" 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "Missing dependencies! Installing..."
    pip3 install -r "$DIR/requirements.txt"
fi

echo ""
echo "Starting GPIO Monitor on port 5001..."
echo "Access the interface at: http://$(hostname -I | awk '{print $1}'):5001"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the application
cd "$DIR"
python3 gpio_monitor.py
