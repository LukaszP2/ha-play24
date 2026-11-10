from datetime import timedelta

DOMAIN = "play24"
CONF_JSESSIONID = "jsessionid"
CONF_DWRSESSIONID = "dwrsessionid"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

DEFAULT_SCAN_INTERVAL_HOURS = 6
DEFAULT_SCAN_INTERVAL = timedelta(hours=DEFAULT_SCAN_INTERVAL_HOURS)

SCAN_INTERVAL_OPTIONS = {
    1: "1h",
    3: "3h",
    6: "6h",
    12: "12h",
    24: "24h",
}

