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
        merge: bool = True,
        confirmed: bool = True,
    ) -> None:
        """Replace the device's downlink queue, keeping other channels intact.

        `down/replace` (not push) so that per channel (fPort) the latest
        command always wins - for a Class A device only the newest desired
        state matters. `confirmed` makes the network server retransmit after
        every uplink until the device acknowledges, which bridges lost RX
        windows without any HA-side retry.

        The pending queue is read first (best effort) and every entry on a
        *different* fPort is re-scheduled unchanged, so e.g. an alert text on
        fPort 13 never wipes a waiting switch command on fPort 12.

        With `raw` the wire-format bytes are scheduled directly (frm_payload) -
        no dependency on the application's downlink payload formatter. With
        `merge` (switch commands only), pending same-fPort mask/values frames
        are folded bit-wise into the new frame (the new command wins on
        overlapping bits). Without `merge` (e.g. text payloads) the new frame
        simply replaces any pending same-fPort entry.

        With `decoded` the JSON is scheduled instead and TTN's encodeDownlink
        turns it into the wire format (fallback for uplink decoders that do not
        announce the downlink bit yet); never merged.
        """

        entry = self.config_entry
        url = (
            f"https://{entry.data[CONF_HOST]}/api/v3/as/applications/"
            f"{entry.data[CONF_APP_ID]}/devices/{device_id}/down/replace"
        )
        downlink: dict = {
            "f_port": fport,
            "confirmed": confirmed,
            "priority": "NORMAL",
        }

        pending = await self._pending_queue_items(device_id)
        preserved = [item for item in pending if item.get("f_port") != fport]

        if raw is not None:
            if merge:
                queued: bytes | None = None
                merged_count = 0
                for item in pending:
                    if item.get("f_port") != fport:
                        continue
                    frame = _decode_switch_frame(item)
                    if frame is None:
                        continue
                    queued = (
                        frame
                        if queued is None
                        else _merge_switch_frames(queued, frame)
                    )
                    merged_count += 1
                if queued is not None:
                    raw = _merge_switch_frames(queued, raw)
                    _LOGGER.info(
                        "Merged downlink for %s with %d pending command(s)",
                        device_id,
                        merged_count,
                    )
            downlink["frm_payload"] = base64.b64encode(raw).decode()
        else:
            downlink["decoded_payload"] = decoded
        body = {"downlinks": [*preserved, downlink]}

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

    async def _pending_queue_items(self, device_id: str) -> list[dict]:
        """Return the downlink queue items still pending for `device_id`.

        Every item is reduced to the keys a `down/replace` accepts back
        (f_port, payload, confirmed, priority) so foreign-fPort entries can be
        re-scheduled verbatim. Best effort: any failure (HTTP error, timeout,
        unexpected body) is logged and yields an empty list - a command must
        go out even when the queue cannot be read; it is then scheduled
        without preservation/merge, which matches the pre-1.3 behavior.
        """
        entry = self.config_entry
        url = (
            f"https://{entry.data[CONF_HOST]}/api/v3/as/applications/"
            f"{entry.data[CONF_APP_ID]}/devices/{device_id}/down"
        )
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {entry.data[CONF_API_KEY]}"},
                timeout=aiohttp.ClientTimeout(total=DOWNLINK_TIMEOUT_S),
            ) as response:
                if response.status >= 400:
                    _LOGGER.warning(
                        "Could not read the downlink queue of %s (HTTP %s) - "
                        "scheduling unmerged",
                        device_id,
                        response.status,
                    )
                    return []
                body = await response.json()
        except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.warning(
                "Could not read the downlink queue of %s (%s) - scheduling unmerged",
                device_id,
                err,
            )
            return []

        items: list[dict] = []
        for item in body.get("downlinks") or []:
            if not isinstance(item, dict) or not isinstance(item.get("f_port"), int):
                continue
            clean: dict = {"f_port": item["f_port"]}
            if isinstance(item.get("frm_payload"), str):
                clean["frm_payload"] = item["frm_payload"]
            elif isinstance(item.get("decoded_payload"), dict):
                clean["decoded_payload"] = item["decoded_payload"]
            else:
                continue
            clean["confirmed"] = bool(item.get("confirmed", False))
            if isinstance(item.get("priority"), str):
                clean["priority"] = item["priority"]
            items.append(clean)
        return items


def _decode_switch_frame(item: dict) -> bytes | None:
    """Decode a queue item into a mask/values frame, or None if it is not one.

    The mask/values wire format comes in byte pairs; anything else was not
    produced by this integration's switch channel - leave it out of the merge.
    """
    payload = item.get("frm_payload")
    if not isinstance(payload, str):
        return None
    try:
        frame = base64.b64decode(payload)
    except (ValueError, TypeError):
        return None
    if frame and len(frame) % 2 == 0:
        return frame
    return None


def _merge_switch_frames(pending: bytes, new: bytes) -> bytes:
    """Merge two mask/values wire-format frames; `new` wins on overlapping bits.

    Frames are sequences of [mask][values] byte pairs (pair k covers switch
    bits 8k..8k+7). The merged frame commands every switch addressed by either
    frame; where both address the same switch, the new value applies. Bits
    outside the merged mask stay 0 and are ignored by the device.
    """
    size = max(len(pending), len(new))
    pending = pending.ljust(size, b"\x00")
    new = new.ljust(size, b"\x00")
    merged = bytearray(size)
    for k in range(0, size, 2):
        old_mask, old_values = pending[k], pending[k + 1]
        new_mask, new_values = new[k], new[k + 1]
        merged[k] = old_mask | new_mask
        merged[k + 1] = (old_values & old_mask & ~new_mask) | (new_values & new_mask)
    return bytes(merged)
