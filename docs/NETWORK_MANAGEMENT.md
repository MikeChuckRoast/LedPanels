# Raspberry Pi Network Interface Management

## Check Interface Status

```bash
# List all interfaces with IP addresses
ip addr show

# Compact view
ip -brief addr show

# Show connection profiles and which device they're on
nmcli connection show

# Show device status
nmcli device status
```

## Connect to WiFi

```bash
# Scan for networks on a specific adapter
nmcli device wifi list ifname wlan1

# Connect to a WPA2 network
nmcli device wifi connect "YourSSID" password "YourPassword" ifname wlan1

# Connect to a hidden network
nmcli connection add type wifi ifname wlan1 con-name "my-wifi" ssid "YourSSID" \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk "YourPassword"
nmcli connection up my-wifi
```

## Manage Connection Profiles

```bash
# List all saved profiles
nmcli connection show

# Rename a profile
nmcli connection modify preconfigured connection.id "home-wifi"

# Disable autoconnect on a profile
nmcli connection modify "ProfileName" connection.autoconnect no

# Delete a profile
nmcli connection delete "ProfileName"
```

## Enable / Disable an Interface

```bash
# Disconnect (NetworkManager stops managing — won't auto-reconnect)
nmcli device disconnect wlan0

# Reconnect
nmcli device connect wlan0

# Bring interface down at the OS level
sudo ip link set wlan0 down

# Bring it back up (NetworkManager will auto-reconnect)
sudo ip link set wlan0 up

# Force a specific profile to connect
nmcli connection up preconfigured
```

## Hostname and mDNS (.local)

The `panelpi.local` address is provided by two things:

- **Hostname** — set in `/etc/hostname`, managed via:
  ```bash
  sudo hostnamectl set-hostname panelpi
  ```
- **mDNS** — advertised by `avahi-daemon` on all active interfaces:
  ```bash
  systemctl status avahi-daemon
  ```

To restrict avahi to specific interfaces, edit `/etc/avahi/avahi-daemon.conf`:
```ini
[server]
allow-interfaces=wlan0
```
Then restart:
```bash
sudo systemctl restart avahi-daemon
```

The hostname is also referenced in `/etc/hosts`:
```
127.0.1.1    panelpi
```
This is updated automatically by `hostnamectl`.
