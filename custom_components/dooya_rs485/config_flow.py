"""Config flow for Dooya RS485 integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

def hex_or_int(value):
    """Convert hex string to int or return as is if already int."""
    try:
        return int(value, 0)
    except ValueError:
        raise vol.Invalid("Must be an integer or hex (e.g., 0xFE)")

def validate_device_id(value):
    """Validate device ID is within valid range."""
    value = hex_or_int(value)
    if not 0 <= value <= 255:
        raise vol.Invalid("Device ID must be between 0 and 255")
    return value

DATA_SCHEMA = vol.Schema({
    vol.Required("name", description="Name of the curtain"): str,
    vol.Required("tcp_address", description="IP address of the RS485 gateway"): str,
    vol.Required("tcp_port", description="TCP port of the RS485 gateway"): int,
    vol.Required(
        "device_id_l",
        description="Low byte of device ID (0-255 or 0x00-0xFF)"
    ): str,
    vol.Required(
        "device_id_h",
        description="High byte of device ID (0-255 or 0x00-0xFF)"
    ): str,
})

class DooyaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dooya RS485."""

    VERSION = 1
    CONNECTION_CLASS = "local_polling"

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Validate device IDs
                device_id_l = validate_device_id(user_input["device_id_l"])
                device_id_h = validate_device_id(user_input["device_id_h"])
                
                # Update user input with validated values
                user_input["device_id_l"] = device_id_l
                user_input["device_id_h"] = device_id_h
                
                # Create unique ID from name
                unique_id = f"dooya_{user_input['name'].lower().replace(' ', '_')}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input["name"],
                    data=user_input
                )
            except ValueError as err:
                errors["base"] = str(err)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
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
                # Validate device IDs
                device_id_l = validate_device_id(user_input["device_id_l"])
                device_id_h = validate_device_id(user_input["device_id_h"])
                
                # Update user input with validated values
                user_input["device_id_l"] = device_id_l
                user_input["device_id_h"] = device_id_h
                
                return self.async_create_entry(title="", data=user_input)
            except ValueError as err:
                errors["base"] = str(err)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "name",
                    default=self.config_entry.data.get("name")
                ): str,
                vol.Required(
                    "tcp_address",
                    default=self.config_entry.data.get("tcp_address")
                ): str,
                vol.Required(
                    "tcp_port",
                    default=self.config_entry.data.get("tcp_port")
                ): int,
                vol.Required(
                    "device_id_l",
                    default=hex(self.config_entry.data.get("device_id_l"))
                ): str,
                vol.Required(
                    "device_id_h",
                    default=hex(self.config_entry.data.get("device_id_h"))
                ): str,
            }),
            errors=errors
        )
