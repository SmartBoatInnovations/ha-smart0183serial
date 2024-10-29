"""Smart Boat 0183 SERIAL Integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging

DOMAIN = "smart0183serial"

_LOGGER = logging.getLogger(__name__)

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Options for Smart0183SERIAL have been updated - applying changes")
    # Reload the integration to apply changes
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup(hass: HomeAssistant, config: dict):
    _LOGGER.debug("Setting up Smart0183SERIAL integration")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Setting up Smart0183SERIAL integration entry: %s", entry.as_dict())
    hass.data.setdefault(DOMAIN, {})

    # Register the update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    
    _LOGGER.debug("Smart0183SERIAL entry setup completed successfully and update listener registered")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading Smart0183SERIAL integration entry: %s", entry.as_dict())
    hass.data[DOMAIN].pop(entry.entry_id)
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    _LOGGER.debug("Smart0183SERIAL entry unloaded successfully")
    return True

