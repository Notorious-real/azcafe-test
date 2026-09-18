# AZ Cafe — Deployment Guide

Two apps: **AZ Cafe Admin** (counter PC) and **AZ Cafe Client** (each gaming PC).
Clients find the server through `client_config.json` or the `AZCAFE_SERVER_IP`
environment variable — no file editing or rebuilding needed.

---

## STEP 0 — What you need

| Item | Notes |
|------|-------|
| Admin PC | Windows 10/11, always on, wired to the shop router |
| Gaming PCs | Windows 10/11, one client per PC |
| Python 3.11+ | Only on the PC where you build (python.org) |
| Inno Setup 6 | Optional — builds one-click installers (jrsoftware.org) |

---

## STEP 1 — Build

1. Install Python 3.11 and tick **"Add python.exe to PATH"**.
2. Double-click **`BUILD.bat`**.
3. Wait 5–10 minutes. When it finishes you get:

```
dist/AZCafe_Admin/     ← counter PC
dist/AZCafe_Client/    ← every gaming PC
installer_output/      ← AZCafe_Admin_Setup.exe, AZCafe_Client_Setup.exe (if Inno Setup is installed)
```

---

## STEP 2 — Admin PC

**Option A — installer (recommended)**
1. Copy `installer_output\AZCafe_Admin_Setup.exe` to the counter PC and run it.
2. Leave *"Allow client PCs to connect"* ticked — it adds the firewall rule for port **5555**.
3. Start **AZ Cafe Admin** from the desktop shortcut.

**Option B — folder copy**
1. Copy `dist/AZCafe_Admin/` to `C:\AZCafe\Admin\` and run `AZCafe_Admin.exe`.
2. Allow port 5555 through Windows Firewall (see the bottom of this file).
3. Right-click the card grid → **Manage Groups…** to set up group names.
4. **Settings → Pricing** for hourly rates, plans and time packages.
5. **Settings → Games** to choose the titles that appear on client PCs.
6. **Settings → Printer** to pick the receipt printer (and test it).
7. Change the default password: **Settings → Security**. Default is `admin123`.

Find the LAN IP the clients will use: `ipconfig` → *IPv4 Address* (e.g. `192.168.1.10`).

---

## STEP 3 — Client PC (repeat for every gaming PC)

**Option A — installer (recommended)**
1. Copy `installer_output\AZCafe_Client_Setup.exe` to the PC and run it.
2. Enter the admin PC's IP when asked (e.g. `192.168.1.10`).
3. Leave *"Start AZ Cafe Client automatically"* ticked.
4. The client starts and shows the lock screen.

**Option B — quick script**
1. Copy the `dist/AZCafe_Client/` folder to the PC.
2. Right-click **`INSTALL_CLIENT.bat`** → *Run as administrator*.
3. Type the admin PC's IP when prompted. The script copies the app to
   `%LOCALAPPDATA%\AZCafe\Client`, saves the address and enables autostart.

**Option C — manual**
1. Copy `dist/AZCafe_Client/` wherever you like and run `AZCafe_Client.exe` once.
2. When it says it is not configured, open
   `%PROGRAMDATA%\AZCafe\client_config.json` and set:

```json
{ "server_ip": "192.168.1.10", "server_port": 5555 }
```

3. Enable autostart:

```
setup_autostart.py --exe "C:\Path\AZCafe_Client.exe"      (registry Run key)
setup_autostart.py --exe "C:\Path\AZCafe_Client.exe" --task  (15 s delayed start)
setup_autostart.py --status        (inspect)
setup_autostart.py --remove        (undo)
```

---

## STEP 4 — Test

1. Start **AZ Cafe Admin**.
2. Start **AZ Cafe Client** on one gaming PC — its card appears on the grid.
3. Right-click the card → **Start Session** → pick member or guest, minutes, payment.
4. The lock screen disappears; the timer overlay shows the countdown.
5. Click the card → **Stop** → the receipt window appears (auto-prints if enabled).
6. Unplug the network cable mid-session: the card shows **SESSION HELD**, and the
   session resumes when the PC reconnects.

---

## Daily operation

| Task | Where |
|------|-------|
| Add / top up a member | **Members** → *Add Member* / *Top Up*, or *Import CSV* |
| Import the old Cyber Cafe Pro export | **Members → Import CSV** (previews first, then imports) |
| Extend a running session | Right-click card → **Add Time**, or **Sessions → Add time** |
| Messages to one PC / all PCs | Right-click card → *Message* (per PC) or toolbar *Message All* |
| Shut down / restart PCs | Toolbar → *Restart All* / *Shut Down All* |
| Day report / export | **Reports** → CSV, Excel or PDF; the *Cash Log* tab lists every payment |
| Backup | **Settings → Data & Backup → Back up now** (keeps the last 30) |

---

## Where your data lives

```
%PROGRAMDATA%\AZCafe\
├── azcafe.db            ← members, sessions, ledger (back this up)
├── backups\             ← automatic daily backups
├── logs\                ← server + client logs (send these when reporting a bug)
├── games.json           ← game launcher list (Admin → Settings → Games)
└── client_config.json   ← on client PCs: server address
```

Reinstalling or updating the app never touches this folder.
If `AZCAFE_DATA_DIR` is set, it is used instead (handy for testing).

---

## Windows Firewall (admin PC, if you used Option B)

1. Windows Defender Firewall → *Advanced Settings*
2. Inbound Rules → *New Rule* → Port → TCP → **5555** → Allow
3. Name it **AZ Cafe Server**

Or from an elevated Command Prompt:

```
netsh advfirewall firewall add rule name="AZ Cafe Server" dir=in action=allow protocol=TCP localport=5555
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Client says *"Server not configured"* | Set `server_ip` in `%PROGRAMDATA%\AZCafe\client_config.json` or the `AZCAFE_SERVER_IP` variable |
| Client card not appearing | Admin app running? Same LAN? Port 5555 allowed? Try `ping` between PCs |
| "Connection refused" on client | Start the admin app first — the client retries every few seconds |
| Lock screen not fullscreen | Windows display scaling above 100% can shrink it; the client retries |
| Kiosk keys still work | Ctrl+Alt+Del cannot be blocked by any app by design; Alt+Tab/Win keys are blocked |
| Receipts don't print | **Settings → Printer** → *Refresh printers* → pick it → *Test print* |
| .exe won't open | Install the Visual C++ Redistributable from Microsoft |
| Need to see what went wrong | Logs in `%PROGRAMDATA%\AZCafe\logs\` |

---

## Updating to a new build

1. Run `BUILD.bat` again.
2. Run the new installer (or copy the new `dist` folder) over the old app folder on
   each PC. Your database, backups and settings are kept — they live in
   `%PROGRAMDATA%\AZCafe`.
