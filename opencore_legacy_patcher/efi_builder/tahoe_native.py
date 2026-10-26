"""Opt-in Tahoe-only Intel native Wi-Fi and SimpleHDA configuration.

This is a preparation helper, not part of automatic model configuration. It
does not distribute community payloads or infer hardware support from SMBIOS.
"""

import copy


NATIVE_BUNDLES = {
    "AirportItlwm-Tahoe.kext": "AirportItlwm",
    "AppleALC-Tahoe.kext": "AppleALC",
    "SimpleHDA.kext": "SimpleHDA",
}


def kernel_version(value: str, upper: bool = False) -> tuple:
    if not value:
        return (999, 999, 999) if upper else (0, 0, 0)
    parts = tuple(int(part) for part in value.split("."))
    if len(parts) > 3:
        raise ValueError("Invalid Darwin version")
    return parts + (0,) * (3 - len(parts))


def active_kexts(config: dict, version: str) -> list:
    """Return effective x86_64 entries, ignoring range syntax after filtering."""
    current = kernel_version(version)
    entries = []
    for item in config["Kernel"]["Add"]:
        if not item["Enabled"] or item.get("Arch", "Any") not in ("Any", "x86_64"):
            continue
        if kernel_version(item.get("MinKernel", "")) <= current <= kernel_version(item.get("MaxKernel", ""), True):
            entries.append({key: value for key, value in item.items() if key not in ("MinKernel", "MaxKernel")})
    return entries


def build_tahoe_native_config(original: dict) -> dict:
    """Keep Sequoia's effective config while selecting one Wi-Fi/audio stack on 25.x."""
    config = copy.deepcopy(original)
    entries = config["Kernel"]["Add"]
    if any(item["BundlePath"] in NATIVE_BUNDLES for item in entries):
        raise ValueError("Native Tahoe payloads are already configured")
    alc = [item for item in entries if item["BundlePath"] == "AppleALC.kext" and item["Enabled"]]
    if len(alc) != 1:
        raise ValueError("Expected exactly one working legacy AppleALC entry")
    if not any(item["BundlePath"] == "Lilu.kext" for item in active_kexts(original, "25.6.0")):
        raise ValueError("Lilu must already be active on Tahoe")
    alc[0]["MaxKernel"] = "24.99.99"
    for item in entries:
        if item["BundlePath"] == "itlwm.kext" and item["Enabled"]:
            if kernel_version(item.get("MinKernel", "")) >= (25, 0, 0):
                item["Enabled"] = False
            else:
                item["MaxKernel"] = "24.99.99"

    def entry(bundle: str, executable: str) -> dict:
        return {"Arch": "x86_64", "BundlePath": bundle,
                "Comment": "Explicit native Tahoe candidate; runtime validation required",
                "Enabled": True, "ExecutablePath": f"Contents/MacOS/{executable}",
                "MaxKernel": "25.99.99", "MinKernel": "25.0.0",
                "PlistPath": "Contents/Info.plist"}

    index = entries.index(alc[0]) + 1
    entries[index:index] = [entry("AppleALC-Tahoe.kext", "AppleALC"), entry("SimpleHDA.kext", "SimpleHDA")]
    entries.append(entry("AirportItlwm-Tahoe.kext", "AirportItlwm"))
    validate_native_config(original, config)
    return config


def validate_native_config(original: dict, candidate: dict) -> None:
    """Reject unintended host changes, overlapping drivers and broken load order."""
    before, after = copy.deepcopy(original), copy.deepcopy(candidate)
    before["Kernel"]["Add"] = after["Kernel"]["Add"] = []
    if before != after:
        raise ValueError("Settings outside Kernel/Add changed")
    for version in ("24.0.0", "24.6.0", "24.99.99"):
        if active_kexts(original, version) != active_kexts(candidate, version):
            raise ValueError("Sequoia's effective kernel extension configuration changed")
    for version in ("25.0.0", "25.6.0", "25.99.99"):
        active = [item["BundlePath"] for item in active_kexts(candidate, version)]
        for bundle in NATIVE_BUNDLES:
            if active.count(bundle) != 1:
                raise ValueError("Missing or duplicate native Tahoe payload")
        if "itlwm.kext" in active or "AirportItlwm.kext" in active or "AppleALC.kext" in active:
            raise ValueError("Conflicting legacy Wi-Fi/audio driver remains active on Tahoe")
        if any(name in active for name in ("IO80211FamilyLegacy.kext", "IOSkywalkFamily.kext")):
            raise ValueError("Native Tahoe AirportItlwm cannot use the legacy wireless framework stack")
        for block in candidate["Kernel"].get("Block", []):
            if (block["Enabled"] and block["Identifier"] in ("com.apple.iokit.IO80211Family", "com.apple.iokit.IOSkywalkFamily")
                    and kernel_version(block.get("MinKernel", "")) <= kernel_version(version)
                    <= kernel_version(block.get("MaxKernel", ""), True)):
                raise ValueError("A required native Tahoe wireless dependency is blocked")
        if not active.index("Lilu.kext") < active.index("AppleALC-Tahoe.kext") < active.index("SimpleHDA.kext"):
            raise ValueError("Native audio dependency order is invalid")
    if any(item["BundlePath"] in NATIVE_BUNDLES for item in active_kexts(candidate, "26.0.0")):
        raise ValueError("Experimental payloads must be limited to Darwin 25")
