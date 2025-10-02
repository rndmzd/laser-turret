# GPIO Monitor - Installation Guide

Quick installation guide for Raspberry Pi 5.

## Quick Start (3 Steps)

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-libgpiod gpiod libgpiod-dev
```

### 2. Install Python Dependencies

```bash
cd ~/laser-turret/utils
pip3 install -r requirements.txt
```

### 3. Run the Application

```bash
# Option A: Run directly
python3 gpio_monitor.py

# Option B: Use the startup script
chmod +x start_gpio_monitor.sh
./start_gpio_monitor.sh
```

Access the web interface at: `http://<your-pi-ip>:5001`

---

## Optional: Auto-Start on Boot

To run the GPIO monitor automatically when your Pi boots:

### 1. Edit the service file

Edit `gpio-monitor.service` and update the paths if your installation is not in `/home/pi/laser-turret/utils`:

```ini
WorkingDirectory=/path/to/your/laser-turret/utils
ExecStart=/usr/bin/python3 /path/to/your/laser-turret/utils/gpio_monitor.py
```

### 2. Install the service

```bash
# Copy service file to systemd directory
sudo cp gpio-monitor.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable gpio-monitor.service

# Start the service now
sudo systemctl start gpio-monitor.service
```

### 3. Manage the service

```bash
# Check status
sudo systemctl status gpio-monitor

# View logs
sudo journalctl -u gpio-monitor -f

# Stop the service
sudo systemctl stop gpio-monitor

# Disable auto-start
sudo systemctl disable gpio-monitor
```

---

## Firewall Configuration

If you have a firewall enabled, allow port 5001:

```bash
sudo ufw allow 5001/tcp
```

---

## Testing

After installation, verify everything works:

### 1. Check the application is running

```bash
curl http://localhost:5001
```

### 2. Check GPIO access

```bash
gpiodetect
# Should show: gpiochip4 [gpio-brcmstb] (54 lines)

gpioinfo gpiochip4
# Should show details of all GPIO lines
```

### 3. Open in browser

Navigate to `http://<raspberry-pi-ip>:5001` and you should see the GPIO monitor interface with real-time updates.

---

## Troubleshooting

### Issue: Permission Denied

```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER

# Log out and log back in, then test
groups
# Should include 'gpio'
```

### Issue: Port Already in Use

```bash
# Find what's using port 5001
sudo lsof -i :5001

# Kill the process if needed
sudo kill -9 <PID>
```

### Issue: gpiod not found

```bash
# Install system package
sudo apt-get install python3-libgpiod

# Or install via pip (may require build tools)
pip3 install gpiod
```

### Issue: Module not found errors

```bash
# Reinstall dependencies
pip3 install --force-reinstall -r requirements.txt
```

---

## Network Access

### Access from other devices on your network

1. Find your Pi's IP address:

   ```bash
   hostname -I
   ```

2. Open in browser: `http://<pi-ip-address>:5001`

### Access from outside your network

1. Set up port forwarding on your router (port 5001)
2. Use your public IP or set up dynamic DNS
3. **Security warning**: Consider adding authentication if exposing to the internet

---

## Uninstallation

### Remove the service (if installed)

```bash
sudo systemctl stop gpio-monitor
sudo systemctl disable gpio-monitor
sudo rm /etc/systemd/system/gpio-monitor.service
sudo systemctl daemon-reload
```

### Remove Python packages

```bash
pip3 uninstall -y flask flask-socketio python-socketio gpiod eventlet
```

### Remove system packages (optional)

```bash
sudo apt-get remove python3-libgpiod gpiod libgpiod-dev
```

---

## Next Steps

- Read the [README.md](README.md) for full documentation
- Customize the interface by editing `templates/gpio_monitor.html`
- Extend functionality by modifying `gpio_monitor.py`
- Integrate with your laser-turret project!
