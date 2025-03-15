import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("tcp_address"): str,
    vol.Required("tcp_port"): int,
    vol.Required("device_id_l"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    vol.Required("device_id_h"): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
})

class DooyaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dooya Curtain Motor."""

    VERSION = 1
    CONNECTION_CLASS = "local_polling"

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            unique_id = f"dooya_{user_input['name'].lower().replace(' ', '_')}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DooyaOptionsFlowHandler(config_entry)


class DooyaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("name", default=self.config_entry.data.get("name")): str,
                vol.Required("tcp_address", default=self.config_entry.data.get("tcp_address")): str,
                vol.Required("tcp_port", default=self.config_entry.data.get("tcp_port")): int,
                vol.Required("device_id_l", default=self.config_entry.data.get("device_id_l")): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
                vol.Required("device_id_h", default=self.config_entry.data.get("device_id_h")): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            })
        )
