"""Isolation and conflict regression cases for the opt-in native Tahoe candidate."""

import copy
from pathlib import Path
import plistlib
import tempfile

from ..efi_builder.tahoe_native import build_tahoe_native_config, validate_native_config, active_kexts
from .native_services_transaction import NativeServicesTransaction, file_tree, verify_tree, optional_executable_fingerprint


def validate_tahoe_native_candidate() -> None:
    """Preserve the working Sequoia configuration and reject ambiguous Tahoe stacks."""
    def entry(name, minimum="", maximum=""):
        return {"Arch": "Any", "BundlePath": name, "Enabled": True,
                "MinKernel": minimum, "MaxKernel": maximum, "Comment": "fixture",
                "ExecutablePath": "Contents/MacOS/test", "PlistPath": "Contents/Info.plist"}

    original = {"Kernel": {"Add": [entry("Lilu.kext"), entry("AppleALC.kext"),
                                   entry("AirportItlwm.kext", "24.0.0", "24.99.99"),
                                   entry("itlwm.kext", "25.0.0", "25.99.99")], "Block": []},
                "DeviceProperties": {"Add": {"HDEF": {"layout-id": 13}}},
                "NVRAM": {"boot-args": "keepsyms=1"}, "ACPI": {"Add": []}}
    saved = copy.deepcopy(original)
    candidate = build_tahoe_native_config(original)
    assert saved == original
    assert active_kexts(candidate, "24.6.0") == active_kexts(original, "24.6.0")

    def must_reject(function, *args):
        try:
            function(*args)
        except ValueError:
            return
        raise AssertionError("Unsafe native Tahoe candidate was accepted")

    must_reject(build_tahoe_native_config, candidate)
    bad = copy.deepcopy(original)
    bad["Kernel"]["Add"][0]["Enabled"] = False
    must_reject(build_tahoe_native_config, bad)
    for key in ("DeviceProperties", "ACPI", "NVRAM"):
        bad = copy.deepcopy(candidate)
        bad[key] = {"unexpected": True}
        must_reject(validate_native_config, original, bad)
    bad = copy.deepcopy(candidate)
    bad["Kernel"]["Add"].append(entry("itlwm.kext", "25.0.0", "25.99.99"))
    must_reject(validate_native_config, original, bad)
    bad = copy.deepcopy(candidate)
    bad["Kernel"]["Add"].append(entry("IO80211FamilyLegacy.kext", "25.0.0", "25.99.99"))
    must_reject(validate_native_config, original, bad)
    bad = copy.deepcopy(candidate)
    bad["Kernel"]["Block"].append({"Enabled": True, "Identifier": "com.apple.iokit.IOSkywalkFamily"})
    must_reject(validate_native_config, original, bad)
    bad = copy.deepcopy(candidate)
    entries = bad["Kernel"]["Add"]
    alc = next(i for i, item in enumerate(entries) if item["BundlePath"] == "AppleALC-Tahoe.kext")
    entries[alc], entries[alc + 1] = entries[alc + 1], entries[alc]
    must_reject(validate_native_config, original, bad)
    bad = copy.deepcopy(candidate)
    next(item for item in bad["Kernel"]["Add"] if item["BundlePath"] == "SimpleHDA.kext")["MaxKernel"] = ""
    must_reject(validate_native_config, original, bad)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        elided = root / "AppleHDA"
        assert optional_executable_fingerprint(elided) is None
        elided.write_bytes(b"present executable")
        present = optional_executable_fingerprint(elided)
        assert present is not None
        elided.write_bytes(b"changed executable")
        assert optional_executable_fingerprint(elided) != present
        (root / "OC").mkdir()
        config_path = root / "OC/config.plist"
        old, new = plistlib.dumps({"old": True}), plistlib.dumps({"new": True})
        config_path.write_bytes(old)
        transaction = NativeServicesTransaction.__new__(NativeServicesTransaction)

        def lint_only(args):
            if args[0] == "/usr/bin/plutil":
                plistlib.loads(Path(args[-1]).read_bytes())
            return b""

        transaction.run = lint_only
        transaction.atomic_config(root, new)
        assert config_path.read_bytes() == new
        try:
            transaction.atomic_config(root, b"invalid plist")
        except plistlib.InvalidFileException:
            pass
        else:
            raise AssertionError("Invalid config replaced the previous config")
        assert config_path.read_bytes() == new
        bundle = root / "Bundle"
        bundle.mkdir()
        (bundle / "binary").write_bytes(b"reviewed bytes")
        hashes = file_tree(bundle)
        verify_tree(bundle, hashes)
        (bundle / "binary").write_bytes(b"changed bytes")
        must_reject(verify_tree, bundle, hashes)
        (bundle / "binary").write_bytes(b"reviewed bytes")
        (bundle / "unexpected").write_bytes(b"extra")
        must_reject(verify_tree, bundle, hashes)
        (bundle / "unexpected").unlink()
        (bundle / "link").symlink_to(root)
        must_reject(verify_tree, bundle, hashes)
