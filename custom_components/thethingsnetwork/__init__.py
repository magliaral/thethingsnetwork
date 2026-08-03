"""Support for The Things network."""

import base64
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import CONF_APP_ID, DOMAIN, PLATFORMS, TTN_API_HOST
from .coordinator import TTNCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_DOWNLINK = "send_downlink"

SEND_DOWNLINK_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("fport"): vol.All(vol.Coerce(int), vol.Range(min=1, max=223)),
        vol.Exclusive("text", "payload"): cv.string,
        vol.Exclusive("payload_base64", "payload"): cv.string,
        vol.Optional("confirmed", default=True): cv.boolean,
    }
)


async def _async_send_downlink(hass: HomeAssistant, call: ServiceCall) -> None:
    """Schedule a raw downlink for a device on any configured application."""
    device_id: str = call.data["device_id"]
    fport: int = call.data["fport"]

    if "text" in call.data:
        try:
            raw = call.data["text"].encode("ascii")
        except UnicodeEncodeError as err:
            raise HomeAssistantError(
                "Downlink text must be plain ASCII (umlauts cost LoRa airtime "
                "twice over - please transliterate)"
            ) from err
    elif "payload_base64" in call.data:
        try:
            raw = base64.b64decode(call.data["payload_base64"], validate=True)
        except (ValueError, TypeError) as err:
            raise HomeAssistantError("payload_base64 is not valid base64") from err
    else:
        raise HomeAssistantError("Provide either 'text' or 'payload_base64'")

    if not raw:
        raise HomeAssistantError("Downlink payload must not be empty")
    if len(raw) > 51:
        raise HomeAssistantError(
            f"Downlink payload is {len(raw)} bytes - the EU868 DR0 limit is 51"
        )

    # The device belongs to exactly one TTN application; try them in order.
    coordinators: list[TTNCoordinator] = list(hass.data.get(DOMAIN, {}).values())
    if not coordinators:
        raise HomeAssistantError("No The Things Network entry is configured")

    last_err: HomeAssistantError | None = None
    for coordinator in coordinators:
        try:
            await coordinator.async_push_downlink(
                device_id,
                fport,
                raw=raw,
                merge=False,
                confirmed=call.data["confirmed"],
            )
            return
        except HomeAssistantError as err:
            last_err = err
    raise HomeAssistantError(
        f"Downlink to {device_id} failed on every configured application: {last_err}"
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Establish connection with The Things Network."""

    _LOGGER.debug(
        "Set up %s at %s",
        entry.data[CONF_APP_ID],
        entry.data.get(CONF_HOST, TTN_API_HOST),
    )

    coordinator = TTNCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_DOWNLINK):

        async def _handle(call: ServiceCall) -> None:
            await _async_send_downlink(hass, call)

        hass.services.async_register(
            DOMAIN, SERVICE_SEND_DOWNLINK, _handle, schema=SEND_DOWNLINK_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _LOGGER.debug(
        "Remove %s at %s",
        entry.data[CONF_APP_ID],
        entry.data.get(CONF_HOST, TTN_API_HOST),
    )

    # Unload entities created for each supported platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        del hass.data[DOMAIN][entry.entry_id]
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_DOWNLINK)
    return unload_ok
