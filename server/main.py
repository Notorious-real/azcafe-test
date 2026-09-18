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
        app.post_to_ui(app.update_stats, active, total)
        if getattr(app, "dashboard", None) is not None:
            app.post_to_ui(app.dashboard.on_pc_update, clients)

    def on_status_msg(msg: str):
        app.post_to_ui(app.set_status, msg)

    server = AZCafeServer(
        on_pc_update=on_pc_update,
        on_status_msg=on_status_msg,
        on_session_event=app.on_session_event,
    )
    server.start()

    app.server = server
    app._set_active_nav("🖥️  Dashboard")
    app._show_dashboard()

    if app.dashboard:
        app.dashboard.server = server

    # Recover anything that was running when the app last closed
    held = db.hold_sessions_across_restart()
    if held:
        app.set_status(f"Recovered {held} session(s) from the last run")

    addr = app.network_ip() if hasattr(app, "network_ip") else ""
    app.set_status(f"Server running on port {config.SERVER_PORT}"
                   + (f" — clients connect to {addr}" if addr else "")
                   + " — waiting for PCs")
    app.refresh_revenue()
    app.mainloop()


if __name__ == "__main__":
    main()
