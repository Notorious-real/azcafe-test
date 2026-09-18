# ============================================================
#  AZ Cafe - Configuration
#  Edit these settings before deploying
# ============================================================

# --- Network ---
SERVER_HOST = "0.0.0.0"       # Server listens on all interfaces
SERVER_PORT = 5555             # Port for client-server communication
BUFFER_SIZE = 4096             # Socket buffer size

# --- Admin ---
ADMIN_PASSWORD = "admin123"    # Change this before deploying!

# --- App Info ---
APP_NAME     = "AZ Cafe"
APP_VERSION  = "1.0.0"
CURRENCY     = "Rs"            # PKR

# --- Timing ---
HEARTBEAT_INTERVAL  = 3       # Seconds between client heartbeats
SESSION_TICK        = 1       # Seconds between timer ticks
RECONNECT_DELAY     = 5       # Seconds before client retries connection

# --- Theme ---
COLOR_BG         = "#0a0a0a"   # Main background
COLOR_BG2        = "#141414"   # Card background
COLOR_BG3        = "#1c1c1c"   # Slightly lighter panels
COLOR_RED        = "#cc0000"   # Primary red accent
COLOR_RED_DARK   = "#990000"   # Darker red (hover, borders)
COLOR_RED_BRIGHT = "#ff1a1a"   # Bright red (alerts, highlights)
COLOR_TEXT       = "#f0f0f0"   # Primary text
COLOR_TEXT_DIM   = "#888888"   # Dimmed/secondary text
COLOR_GREEN      = "#00cc44"   # Active/online indicator
COLOR_YELLOW     = "#ffaa00"   # Warning / low time
COLOR_BORDER     = "#2a2a2a"   # Subtle border

# --- PC Status ---
STATUS_FREE      = "FREE"
STATUS_ACTIVE    = "ACTIVE"
STATUS_LOCKED    = "LOCKED"
STATUS_OFFLINE   = "OFFLINE"
STATUS_PAUSED    = "PAUSED"
