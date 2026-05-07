from __future__ import annotations

import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOWED_DOMAINS,
    CONF_ALLOWED_AREAS,
    CONF_ALLOWED_ENTITIES,
    CONF_ALLOWED_PATTERNS,
    CONF_BLOCKED_ENTITIES,
    CONF_BLOCKED_PATTERNS,
    CONF_INCLUDE_ATTRIBUTES,
    CONF_PROVIDE_ENTITIES_LIST,
    CONF_RETURN_ONLY_IDS,
    CONF_TOKEN,
    CONF_TOKEN_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_TOKEN_NAME): selector.TextSelector(),
})


def _build_summary(data: dict[str, Any]) -> str:
    """Build a summary string of the token permissions."""
    parts = []

    domains = data.get(CONF_ALLOWED_DOMAINS, [])
    areas = data.get(CONF_ALLOWED_AREAS, [])
    entities = data.get(CONF_ALLOWED_ENTITIES, [])
    patterns = [
        p.strip()
        for p in data.get(CONF_ALLOWED_PATTERNS, "").split("\n")
        if p.strip()
    ]
    blocked_entities = data.get(CONF_BLOCKED_ENTITIES, [])
    blocked_patterns = [
        p.strip()
        for p in data.get(CONF_BLOCKED_PATTERNS, "").split("\n")
        if p.strip()
    ]

    has_allow = bool(domains or areas or entities or patterns)

    if not has_allow:
        parts.append("Alle Entitäten sind erlaubt")
    else:
        if domains:
            parts.append(f"Domains: {', '.join(domains)}")
        if areas:
            parts.append(f"Bereiche: {', '.join(areas)}")
        if entities:
            ent_preview = ", ".join(entities[:5])
            if len(entities) > 5:
                ent_preview += f" … (+{len(entities) - 5})"
            parts.append(f"Entitäten ({len(entities)}): {ent_preview}")
        if patterns:
            pat_preview = ", ".join(patterns[:3])
            if len(patterns) > 3:
                pat_preview += f" … (+{len(patterns) - 3})"
            parts.append(f"Patterns ({len(patterns)}): {pat_preview}")

    if blocked_entities or blocked_patterns:
        parts.append("")
        parts.append("Gesperrt:")
        if blocked_entities:
            be = ", ".join(blocked_entities[:5])
            if len(blocked_entities) > 5:
                be += f" … (+{len(blocked_entities) - 5})"
            parts.append(f"  Entitäten: {be}")
        if blocked_patterns:
            bp = ", ".join(blocked_patterns[:3])
            if len(blocked_patterns) > 3:
                bp += f" … (+{len(blocked_patterns) - 3})"
            parts.append(f"  Patterns: {bp}")

    has_opts = data.get(CONF_PROVIDE_ENTITIES_LIST, False)
    return_only_ids = data.get(CONF_RETURN_ONLY_IDS, False)
    include_attrs = data.get(CONF_INCLUDE_ATTRIBUTES, True)

    if has_opts or not include_attrs:
        parts.append("")
        parts.append("Optionen:")
        if has_opts:
            extra = " (nur IDs)" if return_only_ids else ""
            parts.append(f"  /entities-Endpoint aktiviert{extra}")
        if not include_attrs:
            parts.append("  Attribute ausgeschlossen")
        if include_attrs:
            parts.append("  Attribute inkludiert")

    return "\n".join(parts)


def _get_domain_options(hass) -> list[selector.SelectOptionDict]:
    """Get sorted domain list from available states."""
    domains = sorted(set(
        state.domain for state in hass.states.async_all()
    ))
    return [selector.SelectOptionDict(value=d, label=d) for d in domains]


class HaReadOnlyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for HA Read-Only API."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None):
        """Step 1: Token name."""
        errors = {}
        if user_input is not None:
            try:
                self._data[CONF_TOKEN_NAME] = user_input[CONF_TOKEN_NAME]
            except Exception as err:
                _LOGGER.exception("Error in step 1: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors,
                )
            return await self.async_step_domains_areas()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def _build_domains_areas_schema(self) -> vol.Schema:
        """Build schema for step 2."""
        domain_options = _get_domain_options(self.hass)
        return vol.Schema({
            vol.Optional(
                CONF_ALLOWED_DOMAINS,
                default=self._data.get(CONF_ALLOWED_DOMAINS, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=domain_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_ALLOWED_AREAS,
                default=self._data.get(CONF_ALLOWED_AREAS, []),
            ): selector.AreaSelector(
                selector.AreaSelectorConfig(multiple=True),
            ),
        })

    async def async_step_domains_areas(self, user_input=None):
        """Step 2: Domains & Areas."""
        errors = {}
        if user_input is not None:
            try:
                raw_domains = user_input.get(CONF_ALLOWED_DOMAINS) or []
                raw_areas = user_input.get(CONF_ALLOWED_AREAS) or []
                self._data[CONF_ALLOWED_DOMAINS] = list(raw_domains)
                self._data[CONF_ALLOWED_AREAS] = list(raw_areas)
            except Exception as err:
                _LOGGER.exception("ConfigFlow error in step 2: %s", err)
                errors["base"] = "unknown"
                schema = await self._build_domains_areas_schema()
                return self.async_show_form(
                    step_id="domains_areas",
                    data_schema=schema,
                    errors=errors,
                )
            return await self.async_step_entities_patterns()

        schema = await self._build_domains_areas_schema()
        return self.async_show_form(
            step_id="domains_areas",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_entities_patterns(self, user_input=None):
        """Step 3: Entities & Wildcard-Patterns."""
        errors = {}
        if user_input is not None:
            try:
                raw_entities = user_input.get(CONF_ALLOWED_ENTITIES) or []
                self._data[CONF_ALLOWED_ENTITIES] = list(raw_entities)
                self._data[CONF_ALLOWED_PATTERNS] = user_input.get(CONF_ALLOWED_PATTERNS) or ""
            except Exception as err:
                _LOGGER.exception("Error in step 3: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="entities_patterns",
                    data_schema=self._build_entities_schema(),
                    errors=errors,
                )
            try:
                return await self.async_step_block_list()
            except Exception as err:
                _LOGGER.exception("Error in step 3->4 transition: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="entities_patterns",
                    data_schema=self._build_entities_schema(),
                    errors=errors,
                )

        return self.async_show_form(
            step_id="entities_patterns",
            data_schema=self._build_entities_schema(),
            errors=errors,
        )

    def _build_entities_schema(self) -> vol.Schema:
        """Build schema for step 3."""
        return vol.Schema({
            vol.Optional(
                CONF_ALLOWED_ENTITIES,
                default=self._data.get(CONF_ALLOWED_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True),
            ),
            vol.Optional(
                CONF_ALLOWED_PATTERNS,
                default=self._data.get(CONF_ALLOWED_PATTERNS, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True),
            ),
        })

    async def async_step_block_list(self, user_input=None):
        """Step 4: Block list."""
        errors = {}
        if user_input is not None:
            try:
                raw_blocked = user_input.get(CONF_BLOCKED_ENTITIES) or []
                self._data[CONF_BLOCKED_ENTITIES] = list(raw_blocked)
                self._data[CONF_BLOCKED_PATTERNS] = user_input.get(CONF_BLOCKED_PATTERNS) or ""
            except Exception as err:
                _LOGGER.exception("Error in step 4: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="block_list",
                    data_schema=self._build_block_schema(),
                    errors=errors,
                )
            return await self.async_step_options_step()

        return self.async_show_form(
            step_id="block_list",
            data_schema=self._build_block_schema(),
            errors=errors,
        )

    def _build_block_schema(self) -> vol.Schema:
        """Build schema for step 4."""
        return vol.Schema({
            vol.Optional(
                CONF_BLOCKED_ENTITIES,
                default=self._data.get(CONF_BLOCKED_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True),
            ),
            vol.Optional(
                CONF_BLOCKED_PATTERNS,
                default=self._data.get(CONF_BLOCKED_PATTERNS, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True),
            ),
        })

    async def async_step_options_step(self, user_input=None):
        """Step 5: API options."""
        errors = {}
        if user_input is not None:
            try:
                self._data[CONF_PROVIDE_ENTITIES_LIST] = bool(
                    user_input.get(CONF_PROVIDE_ENTITIES_LIST, False)
                )
                self._data[CONF_RETURN_ONLY_IDS] = bool(
                    user_input.get(CONF_RETURN_ONLY_IDS, False)
                )
                self._data[CONF_INCLUDE_ATTRIBUTES] = bool(
                    user_input.get(CONF_INCLUDE_ATTRIBUTES, True)
                )
            except Exception as err:
                _LOGGER.exception("Error in step 5: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="options_step",
                    data_schema=self._build_options_schema(),
                    errors=errors,
                )
            return await self.async_step_review()

        return self.async_show_form(
            step_id="options_step",
            data_schema=self._build_options_schema(),
            errors=errors,
        )

    def _build_options_schema(self) -> vol.Schema:
        """Build schema for step 5."""
        return vol.Schema({
            vol.Optional(
                CONF_PROVIDE_ENTITIES_LIST,
                default=self._data.get(CONF_PROVIDE_ENTITIES_LIST, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_RETURN_ONLY_IDS,
                default=self._data.get(CONF_RETURN_ONLY_IDS, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_INCLUDE_ATTRIBUTES,
                default=self._data.get(CONF_INCLUDE_ATTRIBUTES, True),
            ): selector.BooleanSelector(),
        })

    async def async_step_review(self, user_input=None):
        """Step 6: Review & confirm token creation."""
        errors = {}
        if user_input is not None:
            try:
                self._data[CONF_TOKEN] = secrets.token_urlsafe(32)
                return self.async_create_entry(
                    title=self._data[CONF_TOKEN_NAME],
                    data=self._data,
                )
            except Exception as err:
                _LOGGER.exception("Error creating entry: %s", err)
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="review",
                    data_schema=vol.Schema({}),
                    errors=errors,
                    description_placeholders={
                        "token": self._data.get(CONF_TOKEN, "?"),
                        "token_name": self._data.get(CONF_TOKEN_NAME, ""),
                        "summary": _build_summary(self._data),
                    },
                )

        token = secrets.token_urlsafe(32)
        self._data[CONF_TOKEN] = token
        summary = _build_summary(self._data)

        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "token": token,
                "token_name": self._data.get(CONF_TOKEN_NAME, ""),
                "summary": summary,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return HaReadOnlyOptionsFlow(config_entry)


class HaReadOnlyOptionsFlow(config_entries.OptionsFlow):
    """Options flow for HA Read-Only API."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry
        self._data = dict(config_entry.data)

    async def async_step_init(self, user_input=None):
        """Action menu."""
        if user_input is not None:
            action = user_input["action"]
            if action == "regenerate":
                return await self.async_step_regenerate()
            return await self.async_step_edit_entry()

        schema = vol.Schema({
            vol.Required("action"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value="edit", label="Berechtigungen bearbeiten"
                        ),
                        selector.SelectOptionDict(
                            value="regenerate", label="Token neu generieren"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                ),
            ),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_regenerate(self, user_input=None):
        """Confirm token regeneration."""
        if user_input is not None:
            self._data[CONF_TOKEN] = secrets.token_urlsafe(32)
            return self.async_create_entry(
                title=self._entry.title, data=self._data,
            )

        return self.async_show_form(
            step_id="regenerate",
            data_schema=vol.Schema({}),
            description_placeholders={
                "token": self._data.get(CONF_TOKEN, ""),
            },
        )

    async def async_step_edit_entry(self, user_input=None):
        """Start edit wizard."""
        return await self.async_step_edit_domains_areas()

    async def async_step_edit_domains_areas(self, user_input=None):
        """Edit domains & areas."""
        errors = {}
        if user_input is not None:
            self._data[CONF_ALLOWED_DOMAINS] = user_input.get(CONF_ALLOWED_DOMAINS, [])
            self._data[CONF_ALLOWED_AREAS] = user_input.get(CONF_ALLOWED_AREAS, [])
            return await self.async_step_edit_entities_patterns()

        domain_options = _get_domain_options(self.hass)

        schema = vol.Schema({
            vol.Optional(
                CONF_ALLOWED_DOMAINS,
                default=self._data.get(CONF_ALLOWED_DOMAINS, []),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=domain_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                ),
            ),
            vol.Optional(
                CONF_ALLOWED_AREAS,
                default=self._data.get(CONF_ALLOWED_AREAS, []),
            ): selector.AreaSelector(
                selector.AreaSelectorConfig(multiple=True),
            ),
        })

        return self.async_show_form(
            step_id="edit_domains_areas",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_edit_entities_patterns(self, user_input=None):
        """Edit entities & patterns."""
        errors = {}
        if user_input is not None:
            self._data[CONF_ALLOWED_ENTITIES] = user_input.get(CONF_ALLOWED_ENTITIES, [])
            self._data[CONF_ALLOWED_PATTERNS] = user_input.get(CONF_ALLOWED_PATTERNS, "")
            return await self.async_step_edit_block_list()

        schema = vol.Schema({
            vol.Optional(
                CONF_ALLOWED_ENTITIES,
                default=self._data.get(CONF_ALLOWED_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True),
            ),
            vol.Optional(
                CONF_ALLOWED_PATTERNS,
                default=self._data.get(CONF_ALLOWED_PATTERNS, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=True,
                    placeholder="light.kueche_*\nsensor.*\n*_temperature",
                ),
            ),
        })

        return self.async_show_form(
            step_id="edit_entities_patterns",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_edit_block_list(self, user_input=None):
        """Edit block list."""
        errors = {}
        if user_input is not None:
            self._data[CONF_BLOCKED_ENTITIES] = user_input.get(CONF_BLOCKED_ENTITIES, [])
            self._data[CONF_BLOCKED_PATTERNS] = user_input.get(CONF_BLOCKED_PATTERNS, "")
            return await self.async_step_edit_options()

        schema = vol.Schema({
            vol.Optional(
                CONF_BLOCKED_ENTITIES,
                default=self._data.get(CONF_BLOCKED_ENTITIES, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True),
            ),
            vol.Optional(
                CONF_BLOCKED_PATTERNS,
                default=self._data.get(CONF_BLOCKED_PATTERNS, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=True,
                    placeholder="sensor.temp_bad\nlight.garage_*\n*_unused",
                ),
            ),
        })

        return self.async_show_form(
            step_id="edit_block_list",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_edit_options(self, user_input=None):
        """Edit API options."""
        errors = {}
        if user_input is not None:
            self._data[CONF_PROVIDE_ENTITIES_LIST] = user_input.get(
                CONF_PROVIDE_ENTITIES_LIST, False
            )
            self._data[CONF_RETURN_ONLY_IDS] = user_input.get(
                CONF_RETURN_ONLY_IDS, False
            )
            self._data[CONF_INCLUDE_ATTRIBUTES] = user_input.get(
                CONF_INCLUDE_ATTRIBUTES, True
            )
            return await self.async_step_edit_review()

        schema = vol.Schema({
            vol.Optional(
                CONF_PROVIDE_ENTITIES_LIST,
                default=self._data.get(CONF_PROVIDE_ENTITIES_LIST, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_RETURN_ONLY_IDS,
                default=self._data.get(CONF_RETURN_ONLY_IDS, False),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_INCLUDE_ATTRIBUTES,
                default=self._data.get(CONF_INCLUDE_ATTRIBUTES, True),
            ): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="edit_options",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_edit_review(self, user_input=None):
        """Review edited permissions."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._entry.title, data=self._data,
            )

        summary = _build_summary(self._data)
        return self.async_show_form(
            step_id="edit_review",
            data_schema=vol.Schema({}),
            description_placeholders={"summary": summary},
        )
