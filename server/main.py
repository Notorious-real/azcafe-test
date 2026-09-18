# ============================================================
#  AZ Cafe - Admin Entry Point
# ============================================================

import sys
import os

# ── PyInstaller-safe path setup ───────────────────────────────
# When frozen as .exe, __file__ doesn't work normally
# We need to find the root directory reliably
if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    # Running as script
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, ROOT_DIR)

import config
import database as db
from server.admin_app   import AdminApp
from server.server_core import AZCafeServer


def main():
    db.init_db()

    app = AdminApp()

    def on_pc_update(clients: dict):
        active = sum(1 for c in clients.values() if c.status == "ACTIVE")
        total  = len(clients)
        app.after(0, lambda: app.update_stats(active, total))
        if hasattr(app, "dashboard") and app.dashboard:
            app.after(0, lambda: app.dashboard.on_pc_update(clients))

    def on_status_msg(msg: str):
        app.after(0, lambda: app.set_status(msg))

    server = AZCafeServer(
        on_pc_update=on_pc_update,
        on_status_msg=on_status_msg
    )
    server.start()

    app.server = server
    app._set_active_nav("🖥️  Dashboard")
    app._show_dashboard()

    if app.dashboard:
        app.dashboard.server = server

    app.set_status(f"Server running on port {config.SERVER_PORT} — waiting for PCs")
    app.mainloop()


if __name__ == "__main__":
    main()
