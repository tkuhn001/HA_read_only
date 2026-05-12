DOMAIN = "ha_read_only"
VERSION = "0.2.0"

STORAGE_KEY = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

CONF_TOKEN = "token"
CONF_TOKEN_NAME = "token_name"
CONF_ALLOWED_DOMAINS = "allowed_domains"
CONF_ALLOWED_AREAS = "allowed_areas"
CONF_ALLOWED_ENTITIES = "allowed_entities"
CONF_ALLOWED_PATTERNS = "allowed_patterns"
CONF_BLOCKED_ENTITIES = "blocked_entities"
CONF_BLOCKED_PATTERNS = "blocked_patterns"
CONF_PROVIDE_ENTITIES_LIST = "provide_entities_list"
CONF_RETURN_ONLY_IDS = "return_only_ids"
CONF_INCLUDE_ATTRIBUTES = "include_attributes"

HEADER_TOKEN_NAME = "X-HA-READONLY-TOKEN"
API_PREFIX = "/api/ha_read_only"

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_PER_IP = 100
RATE_LIMIT_MAX_PER_TOKEN = 500

# Dynamic config keys (stored in hass.data)
CONF_RATE_LIMIT_WINDOW = "rate_limit_window"
CONF_RATE_LIMIT_MAX_PER_IP = "rate_limit_max_per_ip"
CONF_RATE_LIMIT_MAX_PER_TOKEN = "rate_limit_max_per_token"
CONF_LOG_LEVEL = "log_level"
