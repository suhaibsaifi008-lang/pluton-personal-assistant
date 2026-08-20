from datetime import datetime, timezone
import getpass
import platform
from typing import Any

try:
    import ctypes
except ImportError:
    ctypes = None

from ..security import PermissionLevel
from .base import Tool, _schema
from .registry import ToolRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clock() -> dict[str, Any]:
    return {"now": _now()}


def _system_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "username": getpass.getuser(),
    }
    if ctypes and platform.system() == "Windows":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                info["total_ram_gb"] = round(stat.ullTotalPhys / (1024**3), 2)
                info["available_ram_gb"] = round(stat.ullAvailPhys / (1024**3), 2)
                info["memory_used_percent"] = int(stat.dwMemoryLoad)
        except Exception:
            pass

        try:
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", ctypes.c_byte),
                    ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte),
                    ("Reserved1", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]
            power = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                ac_status = "Plugged in" if power.ACLineStatus == 1 else ("On battery" if power.ACLineStatus == 0 else "Unknown")
                battery_pct = f"{power.BatteryLifePercent}%" if power.BatteryLifePercent != 255 else "No battery"
                info["power_source"] = ac_status
                info["battery_percent"] = battery_pct
        except Exception:
            pass
    return info


def register_system_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "system.info",
            "Get non-sensitive local system information including OS, CPU, RAM usage, battery status, and username.",
            PermissionLevel.LOW,
            _schema({}, []),
            _system_info,
        )
    )
    registry.register(
        Tool(
            "clock.now",
            "Get the current UTC time.",
            PermissionLevel.LOW,
            _schema({}, []),
            _clock,
        )
    )
