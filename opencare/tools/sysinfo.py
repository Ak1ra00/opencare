"""Lightweight system information snapshot (read-only)."""
from __future__ import annotations

import platform
from dataclasses import dataclass, field


@dataclass
class SysInfo:
    sections: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


def _fmt_bytes(n: int) -> str:
    from opencare.core.fmt import human_bytes

    return human_bytes(n)


def collect() -> SysInfo:
    info = SysInfo()
    info.sections["Operating system"] = [
        ("Edition", platform.system() + " " + platform.release()),
        ("Version", platform.version()),
        ("Machine", platform.machine()),
        ("Hostname", platform.node()),
    ]
    try:
        import psutil

        vm = psutil.virtual_memory()
        freq = psutil.cpu_freq()
        info.sections["Processor"] = [
            ("Name", platform.processor() or "Unknown"),
            ("Physical cores", str(psutil.cpu_count(logical=False) or "?")),
            ("Logical processors", str(psutil.cpu_count(logical=True) or "?")),
            ("Current speed", f"{freq.current / 1000:.2f} GHz" if freq else "—"),
        ]
        info.sections["Memory"] = [
            ("Total", _fmt_bytes(vm.total)),
            ("Available", _fmt_bytes(vm.available)),
            ("In use", f"{vm.percent:.0f}%"),
        ]
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append((part.device, f"{_fmt_bytes(usage.free)} free of {_fmt_bytes(usage.total)} ({usage.percent:.0f}% used)"))
            except (PermissionError, OSError):
                continue
        if disks:
            info.sections["Drives"] = disks
        boot = psutil.boot_time()
        import datetime as dt

        up = dt.datetime.now() - dt.datetime.fromtimestamp(boot)
        hrs, rem = divmod(int(up.total_seconds()), 3600)
        info.sections["Uptime"] = [("Since last boot", f"{hrs} h {rem // 60} min")]
    except ImportError:
        pass
    return info
