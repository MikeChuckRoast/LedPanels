# Output Backends

Every display mode renders through the same abstraction in
[`matrix_backend.py`](../matrix_backend.py), so the choice of backend is a
configuration question, not a code question. `get_matrix_backend()` returns a
`(matrix, options, graphics)` triple that mimics the `rgbmatrix` API regardless
of which backend is selected.

## Selection and precedence

`get_matrix_backend()` checks in a fixed order — **ColorLight → FPP → direct /
emulator**. Enabling both ColorLight and FPP is not an error; ColorLight simply
wins.

| Backend | Platform | Privileges | How to enable |
|---|---|---|---|
| ColorLight 5A-75B | Linux/Unix only | root (raw sockets) | `colorlight_enabled = true` |
| FPP / DDP | Any | none | `fpp_enabled = true` |
| Direct `rgbmatrix` | Raspberry Pi | root (GPIO) | neither flag set, `rgbmatrix` installed |
| Emulator | Any | none | neither flag set, `RGBMatrixEmulator` installed |

The last two share a path: `try_import_rgbmatrix()` tries the real `rgbmatrix`
bindings first, then `RGBMatrixEmulator`, then `rgbmatrix_emulator`. If none
import, it returns `(None, None, None)` and the caller fails.

Configure in `[network]` of `config/settings.toml`:

```toml
[network]
colorlight_enabled = false
colorlight_interface = "eth0"     # find with: ip link show

fpp_enabled = false
fpp_host = "192.168.1.50"
fpp_port = 4048
```

Every mode also accepts `--colorlight`, `--colorlight-interface`, `--fpp`,
`--fpp-host` and `--fpp-port` as overrides.

---

## ColorLight 5A-75B

A low-cost FPGA receiver card driven with raw Ethernet frames — no daemon, no
intermediary. The implementation derives from
[PyLights](https://github.com/KAkerstrom/PyLights) and
[Chubby75](https://github.com/q3k/chubby75), with a corrected pixel-count field.

For the wire format, timing, and the reasoning behind the frame ordering, see
**[PROTOCOL_NOTES.md](PROTOCOL_NOTES.md)** — that document is the source of
truth and is kept in sync with [`colorlight_output.py`](../colorlight_output.py).

### Requirements

- ColorLight 5A-75B card (tested on V6.1 through V8.x)
- Direct Ethernet connection between the Pi and the card — not through a switch
  carrying other traffic
- **Linux or Unix.** Windows cannot do this at all: the backend needs
  `socket.AF_PACKET`, which does not exist there. On Windows use FPP instead.
- **root/sudo**, for raw socket access
- Optional: `numpy`, for faster buffer operations

### Usage

```bash
sudo python display_manager.py --config-dir ./config     # with colorlight_enabled = true

# or drive a single mode directly:
sudo python display_event.py --colorlight --colorlight-interface eth0
```

### Performance

Frame transmission is one Ethernet frame per pixel row with a 1 ms inter-row
delay, so cost scales with panel *height*, not total pixels:

| Panel height | Approx. time per frame |
|---|---|
| 32 rows | ~40 ms |
| 64 rows | ~75 ms |
| 128 rows | ~143 ms |

This is fine for scoreboards and rosters, which change a few times per minute.
It is not a video-rate backend. The card buffers the last frame it received, so
you only send when content actually changes.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `AF_PACKET not available` | Running on Windows. Use `--fpp`, or WSL2 with USB Ethernet passthrough. |
| `Permission denied` / bind error | Not root. Re-run with `sudo`. |
| `Failed to bind to interface 'eth0'` | Wrong name or interface down. Check `ip link`; bring it up with `sudo ip link set eth0 up`. |
| Blank display on a cold-booted board | The hardware silently discards its first several frames. `ColorLightMatrix.__init__` sends 6 blank prime frames (~900 ms) to absorb this. If it persists, raise the prime count. |
| Display stuck on the previous frame | Init frames were sent *before* the row data. They must come after — see PROTOCOL_NOTES.md. |
| Artifacts or wrong colours | Pixel count field must be the actual count, not `width / 3` (the PyLights bug). Byte order is BGR, not RGB. |
| Nothing at all | Check `--width`/`--height` match the real panel, HUB75 cabling, panel power, and that you are on the interface actually wired to the card. |

---

## FPP / DDP

Sends pixels over UDP using DDP (Distributed Display Protocol) to a
[Falcon Player](https://github.com/FalconChristmas/fpp) receiver, which owns the
hardware interfacing. This is the portable option — it needs no special
privileges and runs anywhere, including Windows.

```
┌──────────────────┐        ┌─────────────────┐        ┌────────────────┐
│  display_manager │ ──UDP─→│  FPP receiver   │ ──────→│ LED receiver   │
│  (any OS)        │  DDP   │  (Pi, port 4048)│        │ card / panels  │
└──────────────────┘        └─────────────────┘        └────────────────┘
```

### Usage

```bash
# Local FPP on the same machine
python display_event.py --fpp

# Remote FPP receiver
python display_event.py --fpp --fpp-host 192.168.1.100 --fpp-port 4048
```

### First-time FPP setup

1. Install FPP on a Pi from the [releases page](https://github.com/FalconChristmas/fpp/releases) or its SD card image.
2. Open its web interface at `http://<fpp-ip>`.
3. Set the display size to match your panels and choose the output type for your receiver card.
4. Verify with FPP's built-in test patterns before involving this project.
5. Note the IP address and pass it as `--fpp-host`.

### Packet format

One UDP packet per frame, built in
[`fpp_output.py`](../fpp_output.py) `SwapOnVSync()`:

```
Header (9 bytes)
  [0]    0x04   Flags — VER=0, PUSH=1 (display immediately)
  [1]    0x01   Sequence
  [2]    0x01   Data type: RGB
  [3]    0x01   Destination ID
  [4-6]  0x00   Pixel offset (24-bit, big-endian)
  [7-8]  len    Payload length (16-bit, big-endian)
Data
  RGB triples, row-major
```

A 64x32 display is 6,144 bytes of pixel data. Latency on a local network is
roughly 5–10 ms.

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No display, no error | The send is fire-and-forget UDP — nothing reports a bad host. Confirm FPP is reachable at `http://<fpp-ip>` and listening on 4048. |
| Connection refused | Wrong host or port; check firewall rules on the receiver. |
| Poor text rendering | Install Pillow — `FPPFont` falls back to crude pixel blocks without it. |
| Slow frame assembly | Install numpy; the fallback builds buffers with nested Python lists. |

### Multiple displays

`FPPMatrix.__init__` hardcodes destination ID `0x01`. Driving several
independent DDP destinations would require making that a parameter. Pixel
mapping and brightness are configured inside FPP itself — no code changes here.

---

## Choosing between them

| | ColorLight direct | FPP |
|---|---|---|
| Transport | Raw Ethernet (Layer 2) | UDP/IP (DDP) |
| OS support | Linux/Unix only | Any |
| Privileges | root | none |
| Network | Direct cable, not routable | Routable, works over WiFi |
| Extra software | none | FPP must be installed and running |
| Latency | ~40–143 ms per frame, by panel height | ~5–10 ms |

Use **ColorLight** when you have the card, you are on the Pi, and the panel is
cabled directly. Use **FPP** when developing on Windows or Mac, when the display
is across a network, or when you would rather not run as root.
