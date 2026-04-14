# ruff: noqa: PLR0913
"""Implementation of OJMicrolineAPI for UWG5-series thermostats."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import async_timeout
from aiohttp import ClientSession
from yarl import URL

from .const import (
    REGULATION_COMFORT,
    REGULATION_FROST_PROTECTION,
    REGULATION_MANUAL,
    REGULATION_SCHEDULE,
    REGULATION_VACATION,
    UWG5_MODE_HOLD,
    UWG5_MODE_SCHEDULE,
)
from .exceptions import OJMicrolineAuthError, OJMicrolineError
from .models import Thermostat
from .ojmicroline import RequestFunc

UWG5_SCOPES = (
    "ugw.zones ugw.users ugw.profile ugw.buildings ugw.schedules "
    "ugw.thermostats ugw.firmware ugw.linking openid role offline_access"
)


@dataclass
class UWG5API:
    """Controls OJ Microline UWG5-series thermostats."""

    username: str
    password: str
    host: str = "user-api.ojmicroline.com"
    identity_host: str = "identity.ojmicroline.com"
    client_id: str = "mobile_app_client"

    request: RequestFunc = field(default=None, repr=False)  # type: ignore[assignment]
    _access_token: str | None = field(default=None, repr=False)
    _refresh_token: str | None = field(default=None, repr=False)
    _token_expiry: datetime | None = field(default=None, repr=False)

    async def login(self) -> None:
        """Authenticate via OAuth2 Resource Owner Password Credentials grant.

        Raises
        ------
            OJMicrolineAuthError: Authentication failed.

        """
        if self._access_token and self._token_expiry and self._token_expiry > datetime.now(tz=UTC):
            return

        async with ClientSession() as session:
            url = URL.build(
                scheme="https", host=self.identity_host, path="/connect/token"
            )
            async with async_timeout.timeout(30):
                response = await session.post(
                    url,
                    data={
                        "grant_type": "password",
                        "username": self.username,
                        "password": self.password,
                        "client_id": self.client_id,
                        "scope": UWG5_SCOPES,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    ssl=True,
                )

            if response.status != 200:
                msg = "Unable to authenticate, wrong username or password."
                raise OJMicrolineAuthError(msg)

            data = await response.json()

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._token_expiry = datetime.now(tz=UTC) + timedelta(
            seconds=data["expires_in"]
        )

    async def _auth_request(
        self,
        uri: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request with Bearer token."""
        return await self.request(
            uri,
            method=method,
            body=body,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )

    async def _is_away_active(self, building_id: str) -> bool:
        """Check if away mode is active for a building."""
        try:
            data = await self._auth_request(f"awaymode/{building_id}")
            return "data" in data
        except Exception:  # noqa: BLE001
            return False

    async def get_thermostats(self) -> list[Thermostat]:
        """Fetch all thermostats across all buildings."""
        buildings_data = await self._auth_request("buildings")
        thermostats: list[Thermostat] = []

        for building in buildings_data["data"]:
            building_id = building["id"]
            away_active = await self._is_away_active(building_id)
            tree_data = await self._auth_request(
                f"buildings/{building_id}/tree"
            )
            for zone in tree_data["data"]["zones"]:
                zone_name = zone["name"]
                for thermostat_stub in zone["thermostats"]:
                    thermostat_id = thermostat_stub["id"]
                    control_data = await self._auth_request(
                        f"thermostats/{thermostat_id}/control",
                    )
                    detail_data = await self._auth_request(
                        f"thermostats/{thermostat_id}",
                    )
                    schedule_id = (
                        control_data["data"]
                        .get("scheduleData", {})
                        .get("scheduleId")
                    )
                    schedule_data = None
                    if schedule_id:
                        resp = await self._auth_request(
                            f"schedules/{schedule_id}"
                        )
                        schedule_data = resp.get("data")
                    thermostat = Thermostat.from_uwg5_json(
                        control_data["data"],
                        building_id=building_id,
                        zone_name=zone_name,
                        away_active=away_active,
                    )
                    readouts = (
                        detail_data
                        .get("data", {})
                        .get("thermostatReadouts", {})
                    )
                    thermostat.software_version = readouts.get(
                        "softwareVersionNumber", ""
                    )
                    floor = readouts.get("floorTemperature")
                    if floor is not None:
                        thermostat.temperature_floor = round(
                            float(floor) * 100
                        )
                    room = readouts.get("roomTemperature")
                    if room is not None:
                        thermostat.temperature_room = round(
                            float(room) * 100
                        )
                    thermostat.schedule = schedule_data
                    thermostats.append(thermostat)

        return thermostats

    async def get_energy_usage(self, resource: Thermostat) -> list[float]:
        """Fetch energy usage for a thermostat."""
        if not resource.building_id:
            return []

        now = datetime.now(tz=UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        data = await self._auth_request(
            f"energy/usage/building/{resource.building_id}",
            method="POST",
            body={
                "ThermostatIds": [resource.serial_number],
                "Start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "End": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Size": 0,
            },
        )

        return [
            float(bucket.get("consumedWattHours", 0))
            for bucket in data["data"]["histogram"]
        ]

    async def set_regulation_mode(
        self,
        resource: Thermostat,
        regulation_mode: int,
        temperature: int | None,
        duration: int,
    ) -> bool:
        """Set the regulation mode on a thermostat."""
        thermostat_id = resource.serial_number

        if regulation_mode == REGULATION_VACATION:
            await self._auth_request(
                "awaymode",
                method="POST",
                body={
                    "BuildingId": resource.building_id,
                    "TemperatureLimitMax": 5.0,
                    "StartTime": datetime.now(tz=UTC).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "EndTime": (
                        datetime.now(tz=UTC) + timedelta(days=365)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "IsPlanned": False,
                    "ChangeTimestamp": "0001-01-01T00:00:00",
                },
            )
            return True

        if regulation_mode == REGULATION_FROST_PROTECTION:
            await self._auth_request(
                f"thermostats/{thermostat_id}/standby/True",
                method="PUT",
            )
            return True

        # Disable away mode if currently active.
        if resource.vacation_mode:
            await self._auth_request(
                f"awaymode/{resource.building_id}",
                method="DELETE",
            )

        # Take out of standby if needed.
        if resource.is_in_standby:
            await self._auth_request(
                f"thermostats/{thermostat_id}/standby/False",
                method="PUT",
            )

        if regulation_mode == REGULATION_SCHEDULE:
            body: dict[str, Any] = {
                "ModeAction": UWG5_MODE_SCHEDULE,
                "ChangeTimestamp": "0001-01-01T00:00:00",
            }
        elif regulation_mode in (REGULATION_MANUAL, REGULATION_COMFORT):
            setpoint = (temperature or resource.set_point_temperature or 0) / 100
            body = {
                "ModeAction": UWG5_MODE_HOLD,
                "Setpoint": setpoint,
                "ChangeTimestamp": "0001-01-01T00:00:00",
            }
            if regulation_mode == REGULATION_COMFORT:
                hold_end = datetime.now(tz=UTC) + timedelta(minutes=duration)
                body["HoldUntilEndTime"] = hold_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                body["HoldIsPermanent"] = False
            else:
                body["HoldUntilEndTime"] = None
                body["HoldIsPermanent"] = True
        else:
            msg = f"Unsupported regulation mode for UWG5: {regulation_mode}"
            raise OJMicrolineError(msg)

        await self._auth_request(
            f"thermostats/{thermostat_id}/mode",
            method="PUT",
            body=body,
        )
        return True

    async def set_heating_settings(
        self,
        resource: Thermostat,
        *,
        adaptive_heating: bool | None = None,
        open_window_detection: bool | None = None,
        floor_load: int = 100,
        floor_sensor_type: int = 0,
        floor_sensor_offset: float = 0.0,
        room_sensor_offset: float = 0.0,
    ) -> None:
        """Update heating settings for a thermostat.

        Args:
        ----
            resource: The Thermostat model.
            adaptive_heating: Enable/disable adaptive heating.
            open_window_detection: Enable/disable open window detection.
            floor_load: Floor load in watts.
            floor_sensor_type: Floor sensor type.
            floor_sensor_offset: Floor sensor offset.
            room_sensor_offset: Room sensor offset.

        """
        body: dict[str, Any] = {
            "FloorLoad": floor_load,
            "FloorSensorType": floor_sensor_type,
            "FloorSensorOffset": floor_sensor_offset,
            "RoomSensorOffset": room_sensor_offset,
            "IsAdaptiveHeatingEnabled": adaptive_heating or False,
            "IsOpenWindowDetectionEnabled": open_window_detection or False,
            "ChangeTimestamp": "0001-01-01T00:00:00",
        }
        await self._auth_request(
            f"thermostats/{resource.serial_number}/settings/heating",
            method="PUT",
            body=body,
        )

    async def set_display_settings(
        self,
        resource: Thermostat,
        *,
        display_on: bool = True,
        brightness_normal: int = 6,
        brightness_screensaver: int = 3,
        temperature_unit: int = 1,
        screensaver: int = 2,
        screen_lock_enabled: bool = False,
    ) -> None:
        """Update display settings for a thermostat.

        Args:
        ----
            resource: The Thermostat model.
            display_on: Whether the display is on.
            brightness_normal: Normal brightness level.
            brightness_screensaver: Screensaver brightness level.
            temperature_unit: 0=Celsius, 1=Fahrenheit.
            screensaver: Screensaver type.
            screen_lock_enabled: Whether the screen lock is enabled.

        """
        body: dict[str, Any] = {
            "TemperatureUnit": temperature_unit,
            "Screensaver": screensaver,
            "ScreenLockEnabled": screen_lock_enabled,
            "DisplayOn": display_on,
            "BrightnessNormal": brightness_normal,
            "BrightnessScreensaver": brightness_screensaver,
            "ShowMinutesOnly": False,
            "ScreensaverClockScrollingSpeed": 0,
            "ScreensaverClockScrollingInterval": 0,
            "ScreensaverClockTimeFormat": 0,
            "ChangeTimestamp": "0001-01-01T00:00:00",
        }
        await self._auth_request(
            f"thermostats/{resource.serial_number}/settings/display",
            method="PUT",
            body=body,
        )

    async def create_schedule(
        self,
        name: str,
        base_temperature: float,
        schedule_type: int = 2,
    ) -> str:
        """Create a new schedule.

        Args:
        ----
            name: The schedule name.
            base_temperature: Base temperature in Celsius.
            schedule_type: Schedule type (2 = WorkingDaysAndHolidaysSeparately).

        Returns:
        -------
            The ID of the newly created schedule.

        """
        data = await self._auth_request(
            "schedules",
            method="POST",
            body={
                "Name": name,
                "ScheduleType": schedule_type,
                "UsePreset": False,
                "BaseTemperature": base_temperature,
            },
        )
        return data["data"]["scheduleId"]

    async def update_schedule(
        self,
        schedule_id: str,
        name: str,
        base_temperature: float,
        schedules: list[dict[str, Any]],
        schedule_type: int = 2,
    ) -> None:
        """Update an existing schedule.

        Fetches the current schedule first to obtain required metadata,
        then sends the update.

        Args:
        ----
            schedule_id: The schedule UUID.
            name: The schedule name.
            base_temperature: Base temperature in Celsius.
            schedules: List of day group schedule dicts.
            schedule_type: Schedule type (2 = WorkingDaysAndHolidaysSeparately).

        """
        current = await self._auth_request(f"schedules/{schedule_id}")
        current_data = current.get("data", {})

        await self._auth_request(
            "schedules",
            method="PUT",
            body={
                "Id": schedule_id,
                "Name": name,
                "BaseTemperature": base_temperature,
                "ScheduleType": schedule_type,
                "Schedules": schedules,
                "CreationDate": current_data.get("creationDate", ""),
                "DefaultScheduleType": 0,
            },
        )
