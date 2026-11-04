"""Constants for the Return Right RVM integration."""

DOMAIN = "returnright_rvm"

BASE_URL = "https://returnright.sg/px/ab0capi/v10"
ONEMAP_URL = (
    "https://www.onemap.gov.sg/api/common/elastic/search"
    "?searchVal={postcode}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
)
SEARCH_RADIUS_M = 1500
POLL_RADIUS_M = 2000

CONF_MACHINES = "machines"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEBUG = "debug"
DEFAULT_SCAN_INTERVAL_MIN = 5
MIN_SCAN_INTERVAL_MIN = 1
MAX_SCAN_INTERVAL_MIN = 60

BLOCKED_CYCLES_BEFORE_REPAIR = 3
BACKOFF_MAX_MIN = 15
ISSUE_UPSTREAM_BLOCKED = "upstream_blocked"

STATUS_RUNNING = "running"
STATUS_FULL = "full"
STATUS_OFFLINE = "offline"
