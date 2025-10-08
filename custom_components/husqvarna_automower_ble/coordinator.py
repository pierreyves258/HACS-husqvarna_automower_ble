"""Provides the DataUpdateCoordinator."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from automower_ble.mower import Mower
from automower_ble.protocol import ResponseResult
from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from . import HusqvarnaConfigEntry

SCAN_INTERVAL = timedelta(seconds=60)


class HusqvarnaCoordinator(DataUpdateCoordinator[dict[str, str | int]]):
    """Class to manage fetching data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: HusqvarnaConfigEntry,
        mower: Mower,
        address: str,
        channel_id: str,
        model: str,
    ) -> None:
        """Initialize global data updater."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.address = address
        self.channel_id = channel_id
        self.model = model
        self.mower = mower

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and any connection."""
        LOGGER.debug("Shutdown")
        await super().async_shutdown()
        if self.mower.is_connected():
            await self.mower.disconnect()

    async def _async_find_device(self):
        LOGGER.debug("Trying to reconnect")
        await close_stale_connections_by_address(self.address)

        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

        try:
            if await self.mower.connect(device) is not ResponseResult.OK:
                raise UpdateFailed("Failed to connect")
        except BleakError as err:
            raise UpdateFailed("Failed to connect") from err

    async def _async_update_data(self) -> dict[str, str | int]:
        """Poll the device."""
        LOGGER.debug("Polling device")

        data: dict[str, str | int] = {}

        try:
            if not self.mower.is_connected():
                await self._async_find_device()
        except BleakError as err:
            raise UpdateFailed("Failed to connect") from err

        try:
            data["battery_level"] = await self.mower.battery_level()
            LOGGER.debug("battery_level" + str(data["battery_level"]))
            if data["battery_level"] is None:
                await self._async_find_device()
                raise UpdateFailed("Error getting data from device")

            data["activity"] = await self.mower.mower_activity()
            LOGGER.debug("activity:" + str(data["activity"]))
            if data["activity"] is None:
                await self._async_find_device()
                raise UpdateFailed("Error getting data from device")

            data["state"] = await self.mower.mower_state()
            LOGGER.debug("state:" + str(data["state"]))
            if data["state"] is None:
                await self._async_find_device()
                raise UpdateFailed("Error getting data from device")

            data["next_start_time"] = await self.mower.mower_next_start_time()
            LOGGER.debug("next_start_time: " + str(data["next_start_time"]))
#            if data["next_start_time"] is None:
#                await self._async_find_device()
#                raise UpdateFailed("Error getting data from device")

            data["errorCode"] = await self.mower.command("GetError")
            LOGGER.debug("errorCode: " + str(data["errorCode"]))

            data["NumberOfMessages"] = await self.mower.command("GetNumberOfMessages")
            LOGGER.debug("NumberOfMessages: " + str(data["NumberOfMessages"]))

            data["RemainingChargingTime"] = await self.mower.command("GetRemainingChargingTime")
            LOGGER.debug("RemainingChargingTime: " + str(data["RemainingChargingTime"]))

            # workaround for issue21
            try:
                data["statistics"] = await self.mower.command("GetAllStatistics")
                LOGGER.debug("statuses: " + str(data["statistics"]))
            except ValueError as e:
                if "Data length mismatch" in str(e):
                    LOGGER.debug("Known fail on GetAllStatistics - skipping")
                    data["statistics"] = None
                else:
                    raise  # Re-raise the exception if it's not the known ValueError

            data["operatorstate"] = await self.mower.command("IsOperatorLoggedIn")
            LOGGER.debug("IsOperatorLoggedIn: " + str(data["operatorstate"]))

            data["last_message"] = await self.mower.command("GetMessage", messageId=0)
            LOGGER.debug("last_message: " + str(data["last_message"]))


        except BleakError as err:
            LOGGER.error("Error getting data from device")
            await self._async_find_device()
            raise UpdateFailed("Error getting data from device") from err

        return data