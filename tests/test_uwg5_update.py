# pylint: disable=protected-access
# mypy: disable-error-code=attr-defined
"""Test the UWG5API update regulation mode methods."""

import json
from datetime import UTC, datetime, timedelta

import aiohttp
import pytest
from aresponses import Response, ResponsesMockServer  # type: ignore[import]
from freezegun import freeze_time
from ojmicroline_thermostat import (
    OJMicroline,
    OJMicrolineError,
    Thermostat,
)
from ojmicroline_thermostat.const import (
    REGULATION_COMFORT,
    REGULATION_FROST_PROTECTION,
    REGULATION_MANUAL,
    REGULATION_SCHEDULE,
    REGULATION_VACATION,
)
from ojmicroline_thermostat.uwg5 import UWG5API

from . import load_fixtures


def _make_api() -> UWG5API:
    """Create a UWG5API for tests."""
    return UWG5API(
        username="py",
        password="test",
        host="ojmicroline.test.host",
        identity_host="identity.test.host",
    )


def _add_login_response(aresponses: ResponsesMockServer) -> None:
    """Add a successful login response to the mock server."""
    aresponses.add(
        "identity.test.host",
        "/connect/token",
        "POST",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=load_fixtures("uwg5_token.json"),
        ),
    )


def _make_thermostat() -> Thermostat:
    """Create a UWG5 thermostat for tests."""
    data = json.loads(load_fixtures("uwg5_thermostat_control.json"))
    return Thermostat.from_uwg5_json(
        data["data"],
        building_id="57dc7778-4ed3-4382-9e89-5cf2e0bc0f8a",
        zone_name="Default",
    )


@pytest.mark.asyncio
async def test_set_regulation_mode_manual(aresponses: ResponsesMockServer) -> None:
    """Test setting manual mode with a temperature."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/mode",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-13T23:40:43Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()

        result = await client.set_regulation_mode(
            thermostat, REGULATION_MANUAL, 2600
        )
        assert result is True


@pytest.mark.asyncio
@freeze_time("2026-04-13 23:40:00")
async def test_set_regulation_mode_comfort(aresponses: ResponsesMockServer) -> None:
    """Test setting comfort mode with duration."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/mode",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-13T23:40:43Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()

        result = await client.set_regulation_mode(
            thermostat, REGULATION_COMFORT, 2200, 120
        )
        assert result is True


@pytest.mark.asyncio
async def test_set_regulation_mode_schedule(aresponses: ResponsesMockServer) -> None:
    """Test setting schedule mode."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/mode",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-13T23:40:43Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()

        result = await client.set_regulation_mode(thermostat, REGULATION_SCHEDULE)
        assert result is True


@pytest.mark.asyncio
async def test_set_regulation_mode_frost_protection(
    aresponses: ResponsesMockServer,
) -> None:
    """Test setting frost protection (standby) mode."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/standby/True",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-13T23:41:50Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()

        result = await client.set_regulation_mode(
            thermostat, REGULATION_FROST_PROTECTION
        )
        assert result is True


@pytest.mark.asyncio
async def test_set_regulation_mode_vacation(
    aresponses: ResponsesMockServer,
) -> None:
    """Test enabling away (vacation) mode."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/awaymode",
        "POST",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps({"status": {"code": "OK"}}),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()

        result = await client.set_regulation_mode(
            thermostat, REGULATION_VACATION
        )
        assert result is True


@pytest.mark.asyncio
async def test_set_regulation_mode_disable_vacation(
    aresponses: ResponsesMockServer,
) -> None:
    """Test switching from vacation to schedule disables away mode."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/awaymode/57dc7778-4ed3-4382-9e89-5cf2e0bc0f8a",
        "DELETE",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps({"status": {"code": "OK"}}),
        ),
    )
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/mode",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-14T01:00:00Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        thermostat = _make_thermostat()
        thermostat.vacation_mode = True

        result = await client.set_regulation_mode(thermostat, REGULATION_SCHEDULE)
        assert result is True


@pytest.mark.asyncio
async def test_set_heating_settings(aresponses: ResponsesMockServer) -> None:
    """Test updating heating settings."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/settings/heating",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-14T01:31:28Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        await client.login()
        thermostat = _make_thermostat()

        await api.set_heating_settings(
            thermostat,
            adaptive_heating=True,
            open_window_detection=False,
        )


@pytest.mark.asyncio
async def test_set_display_settings(aresponses: ResponsesMockServer) -> None:
    """Test updating display settings."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/thermostats/2cb3e6c5-8cf8-4e7e-943a-42618c34a506/settings/display",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {"data": {"changeTimestamp": "2026-04-14T01:31:19Z"}}
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        await client.login()
        thermostat = _make_thermostat()

        await api.set_display_settings(
            thermostat,
            display_on=True,
            brightness_normal=6,
            brightness_screensaver=3,
        )


@pytest.mark.asyncio
async def test_create_schedule(aresponses: ResponsesMockServer) -> None:
    """Test creating a new schedule."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/schedules",
        "POST",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {
                    "data": {
                        "scheduleId": "d48ab8e5-b66e-44f1-a48d-7115d2c0f7de"
                    },
                    "status": {"code": "OK"},
                }
            ),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        await client.login()

        schedule_id = await api.create_schedule(
            name="Summer",
            base_temperature=21.11,
        )
        assert schedule_id == "d48ab8e5-b66e-44f1-a48d-7115d2c0f7de"


@pytest.mark.asyncio
async def test_update_schedule(aresponses: ResponsesMockServer) -> None:
    """Test updating an existing schedule."""
    _add_login_response(aresponses)
    aresponses.add(
        "ojmicroline.test.host",
        "/schedules/d48ab8e5-b66e-44f1-a48d-7115d2c0f7de",
        "GET",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps(
                {
                    "data": {
                        "creationDate": "2026-04-14T01:49:42Z",
                        "defaultScheduleType": "None",
                    },
                    "status": {"code": "OK"},
                }
            ),
        ),
    )
    aresponses.add(
        "ojmicroline.test.host",
        "/schedules",
        "PUT",
        Response(
            status=200,
            headers={"Content-Type": "application/json"},
            text=json.dumps({"status": {"code": "OK"}}),
        ),
    )
    async with aiohttp.ClientSession() as session:
        api = _make_api()
        client = OJMicroline(api=api, session=session)
        await client.login()

        await api.update_schedule(
            schedule_id="d48ab8e5-b66e-44f1-a48d-7115d2c0f7de",
            name="Summer",
            base_temperature=21.11,
            schedule_type=2,
            schedules=[
                {
                    "Days": [1, 2, 3, 4, 5],
                    "Schedules": [
                        {
                            "Start": "06:00:00",
                            "End": "09:00:00",
                            "Temperature": 28.0,
                        }
                    ],
                },
                {
                    "Days": [6],
                    "Schedules": [],
                },
                {
                    "Days": [0],
                    "Schedules": [],
                },
            ],
        )
