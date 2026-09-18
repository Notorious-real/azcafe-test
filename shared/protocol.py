# AZ Cafe - Shared Protocol
# Commands sent between server and client

class CMD:
    # Server -> Client
    LOCK         = "LOCK"
    UNLOCK       = "UNLOCK"
    START        = "START"
    STOP         = "STOP"
    PAUSE        = "PAUSE"
    RESUME       = "RESUME"
    SHUTDOWN     = "SHUTDOWN"
    RESTART      = "RESTART"
    MESSAGE      = "MESSAGE"
    TIME_UPDATE  = "TIME_UPDATE"
    TIME_WARNING = "TIME_WARNING"

    # Client -> Server
    REGISTER     = "REGISTER"
    HEARTBEAT    = "HEARTBEAT"
    STATUS       = "STATUS"

class STATUS:
    OFFLINE   = "OFFLINE"
    IDLE      = "IDLE"
    ACTIVE    = "ACTIVE"
    PAUSED    = "PAUSED"
    LOCKED    = "LOCKED"

# Network config
DEFAULT_PORT = 5555
HEARTBEAT_INTERVAL = 5
TIMEOUT = 15

# App info
APP_NAME    = "AZ Cafe"
APP_VERSION = "1.0.0"
