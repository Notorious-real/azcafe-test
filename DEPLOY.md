# AZ Cafe — Deployment Guide
## After building the .exe files

---

## STEP 1 — Before Building

Open `client/client_core.py` and set your admin PC's IP:

```python
SERVER_IP = "192.168.1.10"   # ← Change this to your admin PC's LAN IP
```

**How to find your admin PC's IP:**
1. Open Command Prompt on admin PC
2. Type: `ipconfig`
3. Look for "IPv4 Address" (e.g. 192.168.1.10)

---

## STEP 2 — Build Both .exe Files

1. Make sure Python 3.11 is installed (python.org)
2. Double-click **`BUILD.bat`**
3. Wait for it to finish (~3-5 minutes)
4. Two folders will appear in `dist/`:
   - `dist/AZCafe_Admin/`   ← for your admin PC
   - `dist/AZCafe_Client/`  ← for each gaming PC

---

## STEP 3 — Admin PC Setup

1. Copy `dist/AZCafe_Admin/` folder to your admin PC (e.g. `C:\AZCafe\Admin\`)
2. Run `AZCafe_Admin.exe`
3. Pin to taskbar or desktop for easy access

---

## STEP 4 — Client PC Setup (repeat for all 30 PCs)

1. Copy `dist/AZCafe_Client/` folder to client PC (e.g. `C:\AZCafe\Client\`)
2. Run `setup_autostart.py` OR manually:
   - Press `Win + R` → type `shell:startup` → Enter
   - Create a shortcut to `AZCafe_Client.exe` in that folder
3. Restart the PC — client will start automatically

---

## STEP 5 — Test It

1. Start `AZCafe_Admin.exe` on admin PC
2. Start `AZCafe_Client.exe` on one gaming PC
3. The PC card should appear on the admin dashboard automatically
4. Right-click the card → Start Session → enter name and time → click Start
5. Client PC lock screen should disappear and timer overlay should appear

---

## Default Admin Password

```
admin123
```

**Change it:** Open admin app → Settings → Change Password

---

## Folder Structure After Build

```
dist/
├── AZCafe_Admin/
│   ├── AZCafe_Admin.exe     ← Run this on admin PC
│   ├── assets/
│   │   └── logo.png
│   └── (other pyinstaller files)
│
└── AZCafe_Client/
    ├── AZCafe_Client.exe    ← Run this on each gaming PC
    ├── assets/
    │   └── logo.png
    └── (other pyinstaller files)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Client not appearing on dashboard | Check SERVER_IP in client_core.py matches admin PC's IP |
| "Connection refused" on client | Make sure admin app is running first |
| Firewall blocking | Allow port 5555 in Windows Firewall on admin PC |
| Lock screen not going fullscreen | Run client as Administrator |
| .exe won't open | Install Visual C++ Redistributable from Microsoft |

---

## Windows Firewall (Important!)

On the **admin PC**, allow port 5555:
1. Open Windows Defender Firewall
2. Click "Advanced Settings"
3. Inbound Rules → New Rule
4. Port → TCP → 5555 → Allow → Name it "AZ Cafe"
