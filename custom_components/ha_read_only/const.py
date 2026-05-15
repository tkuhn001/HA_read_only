# HA Read-Only API – Home Assistant Integration
# Copyright (c) 2026 T. Kuhn
# Version: 0.3.3 | Datum: 15. Mai 2026
# Lizenz: MIT – Siehe LICENSE-Datei im Repository
#
# DIE SOFTWARE WIRD "AS IS" BEREITGESTELLT, OHNE JEGLICHE GEWÄHRLEISTUNG.
# NUTZUNG AUF EIGENE GEFAHR.

DOMAIN = "ha_read_only"
VERSION = "0.3.3"

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

USAGE_LOG_MAX = 50

# Dynamic config keys (stored in hass.data)
CONF_RATE_LIMIT_WINDOW = "rate_limit_window"
CONF_RATE_LIMIT_MAX_PER_IP = "rate_limit_max_per_ip"
CONF_RATE_LIMIT_MAX_PER_TOKEN = "rate_limit_max_per_token"
CONF_WEBHOOK_URL = "webhook_url"
CONF_WEBHOOK_ON_API = "webhook_on_api_request"
CONF_WEBHOOK_ON_TOKEN = "webhook_on_token_created"
