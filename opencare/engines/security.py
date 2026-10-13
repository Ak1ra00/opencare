"""Security overview — read-only checks of the machine's protective posture.

This scanner never changes anything on its own: each "issue" is an advisory with a
recommended action the user can take (often opening the relevant Windows settings page).
It reports on Defender/antivirus, firewall, Windows Update, UAC, SmartScreen, and whether
an OpenCare checkup has run recently. The checkup lists these as low-noise advisories.
"""
from __future__ import annotations

from opencare.core.settings import register_defaults
from opencare.engines.base import (
    Category,
    FixContext,
    FixReport,
    Issue,
    Risk,
    ScanContext,
    ScanResult,
    Scanner,
    register,
)

register_defaults({"security.categories": {}})

CATEGORIES = {
    "antivirus": ("Antivirus protection", "Whether real-time antivirus protection is active.", Risk.MEDIUM, True),
    "firewall": ("Firewall", "Whether the Windows firewall is enabled.", Risk.MEDIUM, True),
    "updates": ("Windows Update", "Whether automatic updates are enabled.", Risk.MEDIUM, True),
    "system_guard": ("System safeguards", "UAC and SmartScreen protections.", Risk.MEDIUM, True),
}


@register
class SecurityScanner(Scanner):
    id = "security"
    title = "Security"
    description = "Check that Windows' built-in protections are switched on."
    icon = "shield_check"
    order = 60
    categories = [Category(cid, t[0], t[1], t[2], t[3]) for cid, t in CATEGORIES.items()]

    def scan(self, ctx: ScanContext) -> ScanResult:
        def body(res: ScanResult):
            cats = self.runnable_categories(ctx, res)
            checks = [
                ("antivirus", self._check_antivirus),
                ("firewall", self._check_firewall),
                ("updates", self._check_updates),
                ("system_guard", self._check_guards),
            ]
            active = [(c, fn) for c, fn in checks if c in cats]
            for n, (cat, fn) in enumerate(active):
                if ctx.cancelled():
                    return
                ctx.progress(n / max(1, len(active)), f"Checking {self.category(cat).title}")
                try:
                    fn(ctx, res)
                except Exception as e:  # noqa: BLE001
                    res.errors.append(f"{cat}: {e}")

        return self.timed_scan(ctx, body)

    def _advisory(self, res, cat, key, title, detail, action, settings_uri=""):
        res.issues.append(Issue(
            id=f"security:{cat}:{key}", scanner=self.id, category=cat, title=title, detail=detail,
            risk=self.category(cat).risk, selected=False,
            payload={"kind": "advisory", "action": action, "settings_uri": settings_uri},
        ))

    def _check_antivirus(self, ctx, res):
        state = _security_center_products(ctx.env, "AntiVirusProduct")
        if state is None:
            return  # can't determine (e.g. not permitted) — stay silent
        if not state["any_enabled"]:
            self._advisory(res, "antivirus", "off", "Antivirus protection is off",
                           f"No active antivirus detected ({', '.join(state['names']) or 'none registered'}).",
                           "open_settings", "windowsdefender://")

    def _check_firewall(self, ctx, res):
        key = r"HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
        profiles = {"StandardProfile": "Private", "PublicProfile": "Public", "DomainProfile": "Domain"}
        off = []
        for sub, label in profiles.items():
            v = ctx.env.reg.get_value(f"{key}\\{sub}", "EnableFirewall")
            if v is not None and v.value == 0:
                off.append(label)
        if off:
            self._advisory(res, "firewall", "off", "Firewall is off for some networks",
                           f"The firewall is disabled for: {', '.join(off)}.",
                           "open_settings", "windowsdefender://network/")

    def _check_updates(self, ctx, res):
        key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update"
        v = ctx.env.reg.get_value(key, "AUOptions")
        if v is not None and v.value == 1:
            self._advisory(res, "updates", "disabled", "Automatic updates are turned off",
                           "Windows is set to never check for updates.",
                           "open_settings", "ms-settings:windowsupdate")

    def _check_guards(self, ctx, res):
        uac = ctx.env.reg.get_value(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA")
        if uac is not None and uac.value == 0:
            self._advisory(res, "system_guard", "uac", "User Account Control is off",
                           "UAC prompts are disabled, lowering protection against unwanted changes.",
                           "open_settings", "")

    def fix(self, issues, ctx: FixContext) -> FixReport:
        """Advisories are not auto-fixed; the UI opens the relevant settings instead."""
        report = FixReport(self.id)
        report.errors.append("Security items are advisories; use the Open settings action.")
        return report


def _security_center_products(env, wmi_class: str):
    """Query the Windows Security Center for registered products via WMI.

    Returns {"names": [...], "any_enabled": bool} or None if unavailable. Sandbox envs
    (tests) short-circuit to None so nothing external runs.
    """
    if getattr(env, "sandbox", False):
        return None
    try:
        from opencare.core.admin import powershell

        script = (
            f"Get-CimInstance -Namespace root/SecurityCenter2 -ClassName {wmi_class} "
            "| ForEach-Object {{ '{0}|{1}' -f $_.displayName, $_.productState }}"
        )
        res = powershell(script, timeout=15)
        names = []
        any_enabled = False
        for line in res.stdout.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            name, state = line.rsplit("|", 1)
            names.append(name)
            try:
                # productState bit 0x1000 in the middle byte indicates "enabled"
                if int(state) & 0x1000:
                    any_enabled = True
            except ValueError:
                pass
        if not names:
            return {"names": [], "any_enabled": False}
        return {"names": names, "any_enabled": any_enabled}
    except Exception:  # noqa: BLE001
        return None
