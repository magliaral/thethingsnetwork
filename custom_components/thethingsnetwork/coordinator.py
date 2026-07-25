"""The Things Network's integration DataUpdateCoordinator."""

import asyncio
import base64
from datetime import timedelta
import logging

import aiohttp
from ttn_client import TTNAuthError, TTNClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_APP_ID, POLLING_PERIOD_S

_LOGGER = logging.getLogger(__name__)

DOWNLINK_TIMEOUT_S = 10


class TTNCoordinator(DataUpdateCoordinator[TTNClient.DATA_TYPE]):
    """TTN coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            # Name of the data. For logging purposes.
            name=f"TheThingsNetwork_{entry.data[CONF_APP_ID]}",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(
                seconds=POLLING_PERIOD_S,
            ),
        )

        self._client = TTNClient(
            entry.data[CONF_HOST],
            entry.data[CONF_APP_ID],
            entry.data[CONF_API_KEY],
            first_fetch_h=1,
            push_callback=self._push_callback,
        )

    async def _async_update_data(self) -> TTNClient.DATA_TYPE:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            measurements = await self._client.fetch_data()
        except TTNAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            _LOGGER.error("TTNAuthError")
            raise ConfigEntryAuthFailed from err
        else:
            # Return measurements
            _LOGGER.debug("fetched data: %s", measurements)
            return measurements

    async def _push_callback(self, data: TTNClient.DATA_TYPE) -> None:
        _LOGGER.debug("pushed data: %s", data)

        # Push data to entities
        self.async_set_updated_data(data)

    async def async_push_downlink(
        self,
        device_id: str,
        fport: int,
        *,
        raw: bytes | None = None,
        decoded: dict | None = None,
    ) -> None:
        """Replace the device's downlink queue with one confirmed switch command.

        `down/replace` (not push) so that the latest command always wins - for a
        Class A device only the newest desired state matters. `confirmed` makes
        the network server retransmit after every uplink until the device
        acknowledges, which bridges lost RX windows without any HA-side retry.

        With `raw` the wire-format bytes are scheduled directly (frm_payload) -
        no dependency on the application's downlink payload formatter. With
        `decoded` the JSON is scheduled instead and TTN's encodeDownlink turns
        it into the wire format (fallback for uplink decoders that do not
        announce the downlink bit yet).
        """

        entry = self.config_entry
        url = (
            f"https://{entry.data[CONF_HOST]}/api/v3/as/applications/"
            f"{entry.data[CONF_APP_ID]}/devices/{device_id}/down/replace"
        )
        downlink: dict = {
            "f_port": fport,
            "confirmed": True,
            "priority": "NORMAL",
        }
        if raw is not None:
            downlink["frm_payload"] = base64.b64encode(raw).decode()
        else:
            downlink["decoded_payload"] = decoded
        body = {"downlinks": [downlink]}

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {entry.data[CONF_API_KEY]}"},
                timeout=aiohttp.ClientTimeout(total=DOWNLINK_TIMEOUT_S),
            ) as response:
                if response.status in (401, 403):
                    raise HomeAssistantError(
                        f"TTN rejected the downlink for {device_id} "
                        f"(HTTP {response.status}): the API key needs the "
                        "'write downlink application traffic' right"
                    )
                if response.status >= 400:
                    text = (await response.text())[:200]
                    raise HomeAssistantError(
                        f"TTN downlink for {device_id} failed "
                        f"(HTTP {response.status}): {text}"
                    )
        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise HomeAssistantError(
                f"TTN downlink for {device_id} failed: {err}"
            ) from err

        _LOGGER.info(
            "Scheduled confirmed downlink for %s: %s (fPort %s)",
            device_id,
            f"frm_payload={raw.hex()}" if raw is not None else f"decoded={decoded}",
            fport,
        )
