"""Unit tests for the Dooya RS485 protocol layer.

These tests exercise ``const.py`` and ``dooya_rs485.py`` only. Both modules are
free of Home Assistant imports, so they are loaded directly from file (without
executing the package ``__init__``) and need no HA test harness -- just pytest.
"""
import asyncio
import importlib.util
import pathlib
import sys
import types

import pytest

PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "dooya_rs485"

# Create a lightweight package so the relative ``from .const import ...`` in
# dooya_rs485.py resolves without importing the real (HA-dependent) __init__.py.
_pkg = types.ModuleType("dooya_pkg")
_pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("dooya_pkg", _pkg)


def _load(modname):
    full = f"dooya_pkg.{modname}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{modname}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("const")
dooya_rs485 = _load("dooya_rs485")
DooyaController = dooya_rs485.DooyaController


def _controller():
    return DooyaController(tcp_port=8899, tcp_address="192.0.2.1", device_id_l=0x12, device_id_h=0x34)


def _frame(*payload):
    """Build a full device frame (header + payload) with a valid CRC appended."""
    c = _controller()
    body = bytes([const.START_CODE, 0x12, 0x34, *payload])
    return body + c.calculate_crc(body)


def _patch_response(controller, response):
    async def _fake(_cmd):
        return response

    controller._send_command_with_retry = _fake


# --- CRC ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "data,expected",
    [
        (bytes([0x55, 0x12, 0x34, 0x03, 0x01]), "ad8a"),  # open
        (bytes([0x55, 0x12, 0x34, 0x03, 0x02]), "ed8b"),  # close
        (bytes([0x55, 0x12, 0x34, 0x03, 0x03]), "2c4b"),  # stop
        (bytes([0x55, 0x12, 0x34, 0x03, 0x04, 0x1E]), "c8e5"),  # percent 30%
        (bytes([0x55, 0x12, 0x34, 0x01, 0x02, 0x01]), "2b4d"),  # read position
        (bytes([0x55, 0x00, 0x00, 0x02, 0x00, 0x02, 0x12, 0x34]), "507f"),  # program addr
    ],
)
def test_crc_matches_protocol_spec(data, expected):
    assert _controller().calculate_crc(data).hex() == expected


# --- Response validation -----------------------------------------------------

def test_validate_response_accepts_good_frame():
    c = _controller()
    frame = _frame(0x01, 0x01, 0x1E)  # read position reply, data = 30
    assert c._validate_response(frame) == frame


def test_validate_response_rejects_wrong_device():
    c = _controller()
    body = bytes([const.START_CODE, 0xAB, 0xCD, 0x01, 0x01, 0x1E])
    frame = body + c.calculate_crc(body)
    assert c._validate_response(frame) is None  # cross-talk from another motor


def test_validate_response_rejects_bad_crc():
    c = _controller()
    frame = _frame(0x01, 0x01, 0x1E)[:-1] + b"\x00"
    assert c._validate_response(frame) is None


def test_validate_response_rejects_bad_start_byte():
    c = _controller()
    assert c._validate_response(b"\x00\x12\x34\x01\x01\x1e\x00\x00") is None


# --- Position parsing --------------------------------------------------------

def test_read_position_valid():
    c = _controller()
    _patch_response(c, _frame(0x01, 0x01, 0x1E))  # 30%
    assert asyncio.run(c.read_cover_position()) == 30


def test_read_position_fully_open():
    c = _controller()
    _patch_response(c, _frame(0x01, 0x01, 0x64))  # 100%
    assert asyncio.run(c.read_cover_position()) == 100


def test_read_position_no_stroke_returns_none():
    c = _controller()
    _patch_response(c, _frame(0x01, 0x01, 0xFF))
    assert asyncio.run(c.read_cover_position()) is None


def test_read_position_out_of_range_returns_none():
    c = _controller()
    _patch_response(c, _frame(0x01, 0x01, 0x70))  # > 0x64
    assert asyncio.run(c.read_cover_position()) is None


def test_read_position_no_response_returns_none():
    c = _controller()
    _patch_response(c, None)
    assert asyncio.run(c.read_cover_position()) is None


# --- Motor status parsing (0x02 must NOT be an error) ------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        (const.MOTOR_STATUS_STOPPED, const.MOTOR_STATUS_STOPPED),
        (const.MOTOR_STATUS_OPENING, const.MOTOR_STATUS_OPENING),
        (const.MOTOR_STATUS_CLOSING, const.MOTOR_STATUS_CLOSING),
        (const.MOTOR_STATUS_SETTING, const.MOTOR_STATUS_SETTING),
    ],
)
def test_read_motor_status(raw, expected):
    c = _controller()
    _patch_response(c, _frame(0x01, 0x01, raw))
    assert asyncio.run(c.read_motor_status()) == expected


def test_closing_is_not_an_error_value():
    # Regression guard: 0x02 means "closing", there is no error status.
    assert const.MOTOR_STATUS_CLOSING == 0x02
    assert not hasattr(const, "MOTOR_STATUS_ERROR")


# --- Config registers --------------------------------------------------------

def test_read_device_attributes_decodes_all_registers():
    c = _controller()
    responses = {
        const.CURTAIN_READ_WRITE_DIRECTION: 0x01,
        const.CURTAIN_READ_WRITE_MANUAL_ENABLE: 0x00,
        const.CURTAIN_READ_WRITE_SWITCH_PASSIVE: 0x03,
        const.CURTAIN_READ_WRITE_SWITCH_ACTIVE: 0x01,
        const.CURTAIN_READ_WRITE_SOFTWARE_VERSION: 0x2A,
        const.CURTAIN_READ_WRITE_PROTOCOL_VERSION: 0xA4,
    }

    async def _fake(cmd):
        # cmd = [CURTAIN_READ, register, 0x01]
        return _frame(0x01, 0x01, responses[cmd[1]])

    c._send_command_with_retry = _fake
    attrs = asyncio.run(c.read_device_attributes())
    assert attrs == {
        "direction": 0x01,
        "manual_enable": 0x00,
        "switch_type_passive": 0x03,
        "switch_type_active": 0x01,
        "software_version": 0x2A,
        "protocol_version": 0xA4,
    }


# --- Toggle command ----------------------------------------------------------

def test_toggle_sends_negate_command():
    c = _controller()
    sent = {}

    async def _capture(cmd):
        sent["cmd"] = cmd
        return _frame(0x03, 0x0F)

    c._send_command_with_retry = _capture
    asyncio.run(c.toggle())
    assert sent["cmd"] == bytes([const.CURTAIN_COMMAND, const.CURTAIN_COMMAND_TOGGLE])
    assert const.CURTAIN_COMMAND_TOGGLE == 0x0F


# --- write_register (config) -------------------------------------------------

def test_write_register_sends_correct_frame():
    c = _controller()
    sent = {}

    async def _capture(cmd):
        sent["cmd"] = cmd
        return _frame(0x02, 0x03, 0x01)  # device ack

    c._send_command_with_retry = _capture
    ok = asyncio.run(c.write_register(0x03, 0x01))
    assert ok is True
    assert sent["cmd"] == bytes([const.CURTAIN_WRITE, 0x03, 0x01, 0x01])


def test_write_register_returns_false_without_ack():
    c = _controller()

    async def _fake(_cmd):
        return None

    c._send_command_with_retry = _fake
    assert asyncio.run(c.write_register(0x27, 0x02)) is False


# --- read_status / stroke detection -----------------------------------------

def _status_responder(position_byte, motor_byte):
    async def _fake(cmd):
        register = cmd[1]
        if register == const.CURTAIN_READ_WRITE_PERCENT:
            return _frame(0x01, 0x01, position_byte)
        if register == const.CURTAIN_READ_WRITE_MOTOR_STATUS:
            return _frame(0x01, 0x01, motor_byte)
        return None

    return _fake


def test_read_status_stroke_set():
    c = _controller()
    c._send_command_with_retry = _status_responder(0x1E, const.MOTOR_STATUS_CLOSING)
    status = asyncio.run(c.read_status())
    assert status == {"position": 30, "motor_status": const.MOTOR_STATUS_CLOSING, "stroke_set": True}


def test_read_status_no_stroke():
    c = _controller()
    c._send_command_with_retry = _status_responder(const.POSITION_NO_STROKE, const.MOTOR_STATUS_STOPPED)
    status = asyncio.run(c.read_status())
    assert status["position"] is None
    assert status["stroke_set"] is False


def test_read_status_unknown_position():
    c = _controller()
    # Position register unreadable -> stroke_set unknown (None), not False.
    async def _fake(cmd):
        if cmd[1] == const.CURTAIN_READ_WRITE_MOTOR_STATUS:
            return _frame(0x01, 0x01, const.MOTOR_STATUS_STOPPED)
        return None

    c._send_command_with_retry = _fake
    status = asyncio.run(c.read_status())
    assert status["position"] is None
    assert status["stroke_set"] is None


# --- Address programming validation -----------------------------------------

@pytest.mark.parametrize("low,high", [(0x00, 0x10), (0xFF, 0x10), (0x10, 0x00), (0x10, 0xFF)])
def test_program_device_address_rejects_reserved_bytes(low, high):
    c = _controller()
    assert asyncio.run(c.program_device_address(low, high)) is False
