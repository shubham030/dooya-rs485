import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Helper to convert hex strings to int
def hex_or_int(value):
    try:
        # Supports both decimal and hex formats
        return int(value, 0)
    except ValueError:
        raise vol.Invalid("Must be an integer or hex (e.g., 0xFE)")

DATA_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("tcp_address"): str,
    vol.Required("tcp_port"): int,
    vol.Required("device_id_l", description="Device ID Low (0-255 or 0x00-0xFF)"): str,
    vol.Required("device_id_h", description="Device ID High (0-255 or 0x00-0xFF)"): str,
})

class DooyaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dooya Curtain Motor."""

    VERSION = 1
    CONNECTION_CLASS = "local_polling"

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                device_id_l = hex_or_int(user_input["device_id_l"])
                device_id_h = hex_or_int(user_input["device_id_h"])
                
                if not (0 <= device_id_l <= 255 and 0 <= device_id_h <= 255):
                    raise ValueError("Device IDs must be between 0 and 255")
                
                user_input["device_id_l"] = device_id_l
                user_input["device_id_h"] = device_id_h
                
                unique_id = f"dooya_{user_input['name'].lower().replace(' ', '_')}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=user_input["name"], data=user_input)
            except ValueError as err:
                errors["base"] = str(err)

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
        errors = {}

        if user_input is not None:
            try:
                device_id_l = hex_or_int(user_input["device_id_l"])
                device_id_h = hex_or_int(user_input["device_id_h"])
                
                if not (0 <= device_id_l <= 255 and 0 <= device_id_h <= 255):
                    raise ValueError("Device IDs must be between 0 and 255")
                
                user_input["device_id_l"] = device_id_l
                user_input["device_id_h"] = device_id_h
                
                return self.async_create_entry(title="", data=user_input)
            except ValueError as err:
                errors["base"] = str(err)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("name", default=self.config_entry.data.get("name")): str,
                vol.Required("tcp_address", default=self.config_entry.data.get("tcp_address")): str,
                vol.Required("tcp_port", default=self.config_entry.data.get("tcp_port")): int,
                vol.Required("device_id_l", default=hex(self.config_entry.data.get("device_id_l"))): str,
                vol.Required("device_id_h", default=hex(self.config_entry.data.get("device_id_h"))): str,
            }),
            errors=errors
        )
