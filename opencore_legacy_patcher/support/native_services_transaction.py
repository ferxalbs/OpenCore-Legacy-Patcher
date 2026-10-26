"""Guarded USB EFI transaction for an explicitly prepared native Tahoe candidate.

Run as a standalone script beside stage-manifest.json, tahoe_native.py, Kexts,
config-native-tahoe.plist and AppleHDAHALPlugIn.bundle. Payloads and private EFI
identifiers are intentionally not distributed in this repository.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import datetime


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_tree(root: Path) -> dict:
    return {str(path.relative_to(root)): sha(path) for path in root.rglob("*")
            if path.is_file() and not path.is_symlink() and path.name != ".DS_Store" and not path.name.startswith("._")}


def verify_tree(root: Path, expected: dict) -> None:
    if not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")) or file_tree(root) != expected:
        raise ValueError(f"Bundle tree differs from reviewed payload: {root.name}")


class NativeServicesTransaction:
    def __init__(self, base: Path):
        self.base = base.resolve()
        self.plan = json.loads((self.base / "stage-manifest.json").read_text())
        self.backup = self.base / "before-native-services"
        self.receipt = {"time": datetime.datetime.now().astimezone().isoformat(),
                        "windows_efi_touched": False, "system_snapshots_changed": False}

    def run(self, args: list[str]) -> bytes:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with (self.base / "transaction-commands.jsonl").open("a") as stream:
            stream.write(json.dumps({"command": args, "returncode": result.returncode,
                                     "output": result.stdout.decode(errors="replace")}) + "\n")
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace"))
        return result.stdout

    def info(self, identifier: str) -> dict:
        return plistlib.loads(self.run(["/usr/sbin/diskutil", "info", "-plist", identifier]))

    def usb_info(self) -> dict:
        info = self.info(self.plan["usb_partition_uuid"])
        if (info.get("DiskUUID") != self.plan["usb_partition_uuid"]
                or info.get("VolumeUUID") != self.plan["usb_volume_uuid"]
                or info.get("Internal") is not False or info.get("BusProtocol") != "USB"
                or info.get("Size") != 209715200):
            raise ValueError("EFI is not the reviewed external USB partition")
        return info

    def targets(self) -> tuple:
        host = self.info("/")
        system = self.info(self.plan["target_system_uuid"])
        data = self.info(self.plan["target_data_uuid"])
        if host.get("APFSVolumeGroupID") == self.plan["target_group_uuid"]:
            raise ValueError("Run this offline transaction from Sequoia")
        for info, field in ((system, "target_system_uuid"), (data, "target_data_uuid")):
            if info.get("VolumeUUID") != self.plan[field] or info.get("APFSVolumeGroupID") != self.plan["target_group_uuid"]:
                raise ValueError("Tahoe volume identity mismatch")
            if not info.get("MountPoint"):
                raise ValueError("Both Tahoe volumes must already be mounted")
        system, data = Path(system["MountPoint"]), Path(data["MountPoint"])
        if data in (Path("/"), Path("/System/Volumes/Data")):
            raise ValueError("Refusing to write host Data")
        version = plistlib.loads((system / "System/Library/CoreServices/SystemVersion.plist").read_bytes())
        if version["ProductBuildVersion"] != self.plan["target_build"]:
            raise ValueError("Tahoe build changed")
        return system, data

    def protected_files(self, system: Path, data: Path) -> dict:
        paths = [Path("/Library/Extensions/GeForce.kext/Contents/MacOS/GeForce"),
                 Path("/Library/KernelCollections/AuxiliaryKernelExtensions.kc"),
                 Path("/System/Library/CoreServices/OpenCore-Legacy-Patcher.plist"),
                 Path("/System/Library/Extensions/AppleHDA.kext/Contents/MacOS/AppleHDA"),
                 system / "System/Library/CoreServices/OpenCore-Legacy-Patcher.plist",
                 system / "System/Library/KernelCollections/BootKernelExtensions.kc",
                 system / "System/Library/KernelCollections/SystemKernelExtensions.kc",
                 data / "Library/KernelCollections/AuxiliaryKernelExtensions.kc"]
        return {str(path): sha(path) for path in paths}

    def candidate(self, old: bytes) -> bytes:
        new = (self.base / "config-native-tahoe.plist").read_bytes()
        if hashlib.sha256(old).hexdigest() != self.plan["old_config_sha256"] or hashlib.sha256(new).hexdigest() != self.plan["new_config_sha256"]:
            raise ValueError("Active or candidate config changed")
        spec = importlib.util.spec_from_file_location("tahoe_native", self.base / "tahoe_native.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        validator.validate_native_config(plistlib.loads(old), plistlib.loads(new))
        args = plistlib.loads(new)["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].get("boot-args", "")
        if "keepsyms=1" not in args.split():
            raise ValueError("SimpleHDA requires the existing keepsyms=1 setting")
        return new

    def atomic_config(self, root: Path, content: bytes) -> None:
        pending = root / "OC/config.native-pending.plist"
        if pending.exists():
            raise ValueError("Unreviewed pending config already exists")
        with pending.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        self.run(["/usr/bin/plutil", "-lint", str(pending)])
        os.replace(pending, root / "OC/config.plist")
        self.run(["/bin/sync"])

    def apply(self) -> None:
        system, data = self.targets()
        protected = self.protected_files(system, data)
        for directory in (system / "System/Library/Extensions/AppleHDA.kext", data / "Library/Extensions/AppleHDA.kext"):
            if directory.exists():
                raise ValueError("An AppleHDA restoration already exists; avoid a duplicate stack")
        for name, hashes in self.plan["kext_hashes"].items():
            if name not in ("AirportItlwm-Tahoe.kext", "AppleALC-Tahoe.kext", "SimpleHDA.kext"):
                raise ValueError("Unreviewed EFI payload")
            verify_tree(self.base / "Kexts" / name, hashes)
        verify_tree(self.base / "AppleHDAHALPlugIn.bundle", self.plan["hal_hashes"])
        self.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(self.base / "AppleHDAHALPlugIn.bundle")])
        info = self.usb_info()
        device = info["DeviceIdentifier"]
        if not info.get("MountPoint"):
            self.run(["/usr/sbin/diskutil", "mount", "readOnly", device])
            info = self.usb_info()
        root = Path(info["MountPoint"]) / "EFI"
        old = (root / "OC/config.plist").read_bytes()
        new = self.candidate(old)
        if sha(root / "OC/Kexts/Lilu.kext/Contents/MacOS/Lilu") != self.plan["existing_lilu_binary_sha256"]:
            raise ValueError("Installed Lilu changed since binary dependency validation")
        hal = data / "Library/Audio/Plug-Ins/SimpleHDA/AppleHDAHALPlugIn.bundle"
        if hal.exists() or hal.is_symlink():
            raise ValueError("A HAL installation already exists; inspect before replacing it")
        if self.backup.exists():
            raise ValueError("An earlier attempt exists; inspect its receipt before repeating")
        self.backup.mkdir(mode=0o700)
        before = file_tree(root)
        self.run(["/usr/bin/ditto", str(root), str(self.backup / "EFI")])
        if file_tree(self.backup / "EFI") != before:
            raise ValueError("Original EFI backup failed verification")
        for name in self.plan["kext_hashes"]:
            if (root / "OC/Kexts" / name).exists():
                raise ValueError("Destination payload already exists")
        required = sum(path.stat().st_size for path in (self.base / "Kexts").rglob("*") if path.is_file())
        if shutil.disk_usage(root).free < required + 5_000_000:
            raise ValueError("Insufficient free space on USB EFI")
        rw, created, hal_created = False, [], False
        try:
            self.run(["/usr/sbin/diskutil", "unmount", device])
            self.run(["/usr/sbin/diskutil", "mount", device])
            info = self.usb_info()
            root = Path(info["MountPoint"]) / "EFI"
            if not info["Writable"] or file_tree(root) != before:
                raise ValueError("EFI changed between read-only and writable mounts")
            rw = True
            for name, hashes in self.plan["kext_hashes"].items():
                destination = root / "OC/Kexts" / name
                created.append(destination)
                self.run(["/usr/bin/ditto", str(self.base / "Kexts" / name), str(destination)])
                verify_tree(destination, hashes)
            hal.parent.mkdir(parents=True, exist_ok=True)
            hal_created = True
            self.run(["/usr/bin/ditto", str(self.base / "AppleHDAHALPlugIn.bundle"), str(hal)])
            self.run(["/usr/sbin/chown", "-R", "root:wheel", str(hal)])
            self.run(["/bin/chmod", "-R", "u=rwX,go=rX", str(hal)])
            verify_tree(hal, self.plan["hal_hashes"])
            backup_config = root / "OC/config.before-native-services.plist"
            if backup_config.exists():
                raise ValueError("Unreviewed config backup already exists")
            backup_config.write_bytes(old)
            self.atomic_config(root, new)
            expected = dict(before)
            expected["OC/config.plist"] = self.plan["new_config_sha256"]
            expected["OC/config.before-native-services.plist"] = self.plan["old_config_sha256"]
            for name, hashes in self.plan["kext_hashes"].items():
                expected.update({f"OC/Kexts/{name}/{relative}": digest for relative, digest in hashes.items()})
            if file_tree(root) != expected or self.protected_files(system, data) != protected:
                raise ValueError("Unexpected EFI changes or protected file differences")
            self.receipt.update(status="native_tahoe_wifi_audio_staged_reboot_required",
                                config_sha256=self.plan["new_config_sha256"],
                                sequoia_effective_config_unchanged=True, protected_files_unchanged=True,
                                payloads_verified=True, hal_verified=True, runtime_verified=False)
        except Exception as error:
            self.receipt.update(status="failed", error=str(error))
            if rw:
                try:
                    self.atomic_config(root, old)
                    for path in created:
                        if path.exists():
                            shutil.rmtree(path)
                    if hal_created and hal.exists():
                        shutil.rmtree(hal)
                    self.receipt["rollback"] = "prior_config_restored_and_new_payloads_removed"
                except Exception as rollback:
                    self.receipt["rollback_error"] = str(rollback)
            raise
        finally:
            try:
                if self.usb_info().get("MountPoint"):
                    self.run(["/bin/sync"])
                    self.run(["/usr/sbin/diskutil", "unmount", device])
                self.run(["/usr/sbin/diskutil", "mount", "readOnly", device])
                self.receipt["efi_left_read_only"] = not self.usb_info()["Writable"]
            finally:
                (self.base / "native-stage-result.json").write_text(json.dumps(self.receipt, indent=2))
                print(json.dumps(self.receipt, indent=2))

    def restore(self) -> None:
        system, data = self.targets()
        protected = self.protected_files(system, data)
        info = self.usb_info()
        device = info["DeviceIdentifier"]
        if not info.get("MountPoint"):
            self.run(["/usr/sbin/diskutil", "mount", "readOnly", device])
            info = self.usb_info()
        root = Path(info["MountPoint"]) / "EFI"
        if sha(root / "OC/config.plist") != self.plan["new_config_sha256"]:
            raise ValueError("Config changed after native staging; do not overwrite it")
        old = (self.backup / "EFI/OC/config.plist").read_bytes()
        if hashlib.sha256(old).hexdigest() != self.plan["old_config_sha256"]:
            raise ValueError("Original config backup differs")
        hal = data / "Library/Audio/Plug-Ins/SimpleHDA/AppleHDAHALPlugIn.bundle"
        verify_tree(hal, self.plan["hal_hashes"])
        try:
            self.run(["/usr/sbin/diskutil", "unmount", device])
            self.run(["/usr/sbin/diskutil", "mount", device])
            root = Path(self.usb_info()["MountPoint"]) / "EFI"
            self.atomic_config(root, old)
            # Added EFI bundles remain inert for diagnosis; the old config has no references.
            shutil.rmtree(hal)
            if self.protected_files(system, data) != protected:
                raise ValueError("Protected files changed during restore")
            self.receipt.update(status="previous_wifi_audio_config_restored_reboot_required",
                                config_sha256=self.plan["old_config_sha256"], protected_files_unchanged=True)
        finally:
            self.run(["/bin/sync"])
            if self.usb_info().get("MountPoint"):
                self.run(["/usr/sbin/diskutil", "unmount", device])
            self.run(["/usr/sbin/diskutil", "mount", "readOnly", device])
            self.receipt["efi_left_read_only"] = not self.usb_info()["Writable"]
            (self.base / "native-restore-result.json").write_text(json.dumps(self.receipt, indent=2))
            print(json.dumps(self.receipt, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise PermissionError("Run the prepared wrapper with local administrator authentication")
    transaction = NativeServicesTransaction(Path(__file__).resolve().parent)
    if args.restore:
        transaction.restore()
    else:
        transaction.apply()


if __name__ == "__main__":
    main()
