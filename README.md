# Stepper Quests

A Linux tray app that counts steps on a Sportstech DFX100 stepper over
Bluetooth Low Energy and walks them along Frodo's road from Bag End to Mount
Doom. No vendor app, no cloud. Every walk is stored locally, chapters and
waypoints unlock as the lifetime step count grows, and story-tied
achievements pop up as toasts.

It also contains the plain command-line counter and the protocol notes that
came out of reverse engineering the console. The DFX100 is really an
**iConsole+** console (advertises as `iConsole+NNNN`), and the same frame
format is used by other iConsole fitness gear, so the BLE part may work on
more than this one stepper.

## Install

Requires Python 3.10+ and BlueZ (any recent Linux desktop). Tested on Linux
Mint with Cinnamon.

```bash
git clone https://github.com/vossiman/stepperHacking.git
cd stepperHacking
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

Find your console's MAC once (the stepper must be awake and not connected to
the phone app):

```bash
python stepper.py            # scans, lists iConsole devices with their MAC
```

## Tray app

```bash
bin/stepper-quests           # works from any directory, detaches from the terminal
```

On the first start open **Settings...** from the tray menu and enter the
stepper's MAC. The app connects after a restart. Until a MAC is set the icon
stays dashed and the tooltip says so.

Left click the tray icon for the journey window; right click for the menu.
The icon shows grey footprints when idle, brass ones while stepping, and
dashed outlines while the BLE link is down.

The journey window opens on one screen: the chapter you are walking and the
steps to the next waypoint, the route strip, a panel for the walk in
progress (or the last one) and a panel for today with the last seven days.
Below that, tabs hold the detail: Journey (the chapter tree), Achievements,
Records (records, totals and pace projections) and History (the last 30
days). The window refreshes once a second while you step and remembers the
tab you left open.

How counting works: any cadence on the console starts a walk, a minute
without steps ends it, and walks under 20 steps are dropped. Steps are
integrated from the console's cadence (it reports steps per minute only, see
Protocol below). The road is measured in walkable miles: distances Frodo
covered on foot count fully, horse and boat legs are shortened so the whole
journey stays walkable, and the eagles are free. Mileage follows the Eowyn
Challenge tables; sources are listed in `stepper_quests/data/SOURCES.md`.

### Settings (tray menu, Settings...)

- **Stepper MAC**. Takes effect after a restart.
- **Metres per step** (0.40 to 1.20, default 0.70). Changing it moves your
  marker, because progress is recomputed from your lifetime steps.
- **Idle timeout** (10 to 600 s, default 60). A walk ends after this long
  without steps. A change applies from the next walk.
- **Frame logging** (default on). Keeps raw BLE frames and step CSVs per
  walk, useful if the protocol notes below ever need re-checking.

### Data

Everything lives in `~/.local/share/stepper-quests/` (or `$STEPPER_QUESTS_HOME`):

- `steps.db`: SQLite with walks, achievements, reached waypoints and settings. Back this up.
- `data/`: one `frames_*.csv` and `steps_*.csv` per walk when frame logging is on.
- `app.log`: the launcher appends the app's log here.

### Start at login

```bash
sed "s|@REPO@|$PWD|g" stepper-quests.desktop > /tmp/stepper-quests.desktop
install -Dm644 /tmp/stepper-quests.desktop ~/.config/autostart/stepper-quests.desktop
install -Dm644 /tmp/stepper-quests.desktop ~/.local/share/applications/stepper-quests.desktop
```

The second copy registers the app with the desktop so notifications show
its name and icon. Remove both files to undo. Quit from the tray menu; the
running walk is saved, also on logout. A second launch while one instance
runs just raises the window.

### Flags

- `--demo` feeds a scripted 30 second walk instead of BLE, to see the toasts.
- `--demo-seed N` adds one finished N-step walk dated yesterday, if the store is empty.
- `--no-ble` runs without connecting to the stepper.
- `--quest PATH` loads another quest file, for example `tests/fixtures/mini_quest.json`.
- `--idle-timeout SECONDS` overrides the idle timeout for this run.

A run with `--demo` or `--demo-seed` never touches your real data: unless
`STEPPER_QUESTS_HOME` is set it uses a fresh temporary directory and logs
its path at startup.

### Reconnecting

The console drops off BLE when it sleeps and stops advertising. The app
keeps one scan running and listens for the console's MAC, with no timeout.
Step on the stepper to wake it: the app logs `... seen, connecting` and
connects on the first advertisement, so the first steps are counted. If that
connect fails, it waits a short backoff (1, 2, 4, 8, then 15 seconds) and
goes back to listening.

## Command-line counter

```bash
python stepper.py --address AA:BB:CC:DD:EE:FF
```

Step; the counter updates live. Ctrl-C to stop. Flags:

- `--address AA:BB:...` connect straight to that MAC (skips scanning, most reliable).
- (no address) scan and match by name (`iConsole`, `DFX`, ...) or the FFF0 service.
- `--raw` calibration mode: print every notification frame byte by byte.
- `--seconds N` stop automatically after N seconds (0 = until Ctrl-C).

Each session writes `steps_*.csv` (`t, spm, total_steps`) and `frames_*.csv`
(raw frames) to `data/`. If a scan returns zero devices it is usually a
transient BlueZ hiccup; connecting by `--address` avoids it.

## Development

```bash
.venv/bin/python -m pytest        # 200+ tests, headless (offscreen Qt)
```

Layout: `stepper_quests/protocol.py` (frames), `ble.py` (connection loop
and Qt worker), `counter.py` (step integration and walk detection),
`store.py` (SQLite), `quests.py` and `data/frodo.json` (the road),
`progress.py` (waypoints and achievements), `journey_model.py` (numbers
behind the window), the Qt widgets, and `app.py` (tray wiring). Design
notes and the implementation plans are under `docs/superpowers/`.

## Protocol

There is **no authentication** on the BLE link. Earlier "hacking" attempts
stalled only because they used the wrong frame format, not because anything
was locked.

GATT layout, vendor service `FFF0`:

| Characteristic | UUID | Direction |
|---|---|---|
| Write | `0000fff2-0000-1000-8000-00805f9b34fb` | host sends commands |
| Notify | `0000fff1-0000-1000-8000-00805f9b34fb` | device sends replies |

Every frame is `F0 <op> ... <checksum>`, where `checksum = sum(all previous
bytes) & 0xFF`. The device is **poll driven**: it only streams the metrics
frame while the host keeps polling. Commands and their replies pair up as
`A0->B0`, `A1->B1`, `A2->B2`, `A5->B5`.

Init sequence (each value already includes its checksum byte), then poll:

```
F0 A0 00 00 90      hello
F0 A0 01 01 92      init confirm
F0 A1 01 01 93
F0 A5 01 01 02 99
F0 A2 01 01 94      poll / start streaming
...then resend F0 A2 01 01 94 about twice a second
```

### Metrics frame (the reply to the A2 poll)

19 bytes: `F0 B2 00 C8 00 00 00 00 00 SS 00 00 00 00 00 00 00 00 CK`

- byte 0..1 : `F0 B2` header
- byte 3    : constant `0xC8`
- **byte 9  : steps per minute (cadence). The only live field.**
- byte 18   : checksum
- all other bytes: always `0x00`

Verified across 124 captured frames: byte 9 was the sole varying payload
(54 to 68 spm during steady stepping), byte 18 tracked it as the checksum,
every other byte stayed constant.

### Why the step count is computed, not read

The console transmits **steps per minute only**. It sends no cumulative step
total and no elapsed-time field (those byte positions stay zero). So the step
count is integrated on the PC: `steps += spm * dt / 60` across the real time
between frames. Over a steady session this tracks actual steps closely. It is
a software estimate, not an exact device-reported count.

### What cadence means and how it is measured

Byte 9 is an instantaneous rate, not an average and not a total. It jitters
frame to frame during steady effort, which is the signature of a value
recomputed from the timing of each stroke. The console almost certainly has
one magnet and a reed or Hall sensor; each foot press is one pulse, and the
console derives the rate from the time between pulses (roughly
`60 / seconds_between_pulses`). Push faster, the gap shrinks, the number
rises.

Units confirmed by a calibration test: **one step = one single foot press**
(not a left-plus-right stride). 20 deliberate presses read 18 on the
integrated counter. The small shortfall is the 2 Hz sampling rounding off the
first and last press, not a miscount.

### What else is on the bus (probed, nothing hidden)

Polling every opcode A0 through A6 while stepping, and again after changing
the physical resistance, returned:

- **A2 -> B2**: the metrics frame above. Byte 9 (cadence) is the only live value.
- **A0, A1, A4, A5**: each returns one fixed byte (`104`, a `5f` payload,
  `108`, `109`) that never changed, not while stepping and not when
  resistance was changed. Static device or config constants, not workout data.
- **A3, A6**: not answered. A6 is the resistance-set command on the iConsole
  bike; this stepper ignores it.

The **resistance / difficulty setting is not transmitted at all**: every
byte was identical before and after turning it up. It is a mechanical setting
the electronics do not read out. Cadence is the single piece of live data the
console exposes.

## Credit

Frame format and init sequence cross-checked against the `iconsolebike`
parser in the open-source qdomyos-zwift project, then confirmed byte by byte
against this device. Road mileage from the Eowyn Challenge tables, based on
Karen Wynn Fonstad's Atlas of Middle-earth. Tolkien's text is quoted only in
chapter titles and short paraphrases.

## License

MIT, see `LICENSE`.
