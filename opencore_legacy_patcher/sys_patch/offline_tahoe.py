"""Experimental, explicitly targeted offline Kepler recovery for Intel Tahoe.

This standalone tool consumes a reviewed, hashed payload manifest and a previously
built AuxKC. It does not invoke the host-oriented OCLP root patcher, rebuild the
host caches, install launch services, change EFI, or select a default boot disk.
Run --check without root first. Applying requires local administrator access.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import subprocess


KEXT_NAMES = {
    "GeForce.kext", "NVDAGF100Hal.kext", "NVDAGK100Hal.kext",
    "NVDAResman.kext", "NVDAStartup.kext",
}
SYSTEM_PREFIXES = (
    "System/Library/Frameworks/", "System/Library/PrivateFrameworks/",
    "System/Library/Sandbox/Profiles/", "System/Library/Extensions/",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in (".", "..") for p in value.split("/")):
        raise ValueError(f"Unsafe relative path: {value}")
    return Path(path)


def contained_path(root: Path, relative: str) -> Path:
    result = root / relative_path(relative)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes selected volume: {relative}")
    return result


def validate_identities(host: dict, system: dict, data: dict, manifest: dict) -> None:
    group = manifest["target_group_uuid"]
    if host.get("APFSVolumeGroupID") == group:
        raise ValueError("Offline target is the running system")
    for info, key in ((system, "target_system_uuid"), (data, "target_data_uuid")):
        if info.get("VolumeUUID") != manifest[key] or info.get("APFSVolumeGroupID") != group:
            raise ValueError(f"Volume identity mismatch: {key}")
        if info.get("APFSContainerReference") != system.get("APFSContainerReference"):
            raise ValueError("System and Data are in different containers")
    if system.get("VolumeUUID") == data.get("VolumeUUID"):
        raise ValueError("System and Data must be distinct volumes")
    if system.get("MountPoint") == "/" or data.get("MountPoint") in ("/", "/System/Volumes/Data"):
        raise ValueError("Refusing to modify host mount points")


def validate_manifest(manifest: dict) -> None:
    if manifest.get("target_build") != "25G241":
        raise ValueError("This experimental recovery is limited to Tahoe 25G241")
    kexts = set()
    for op in manifest["operations"]:
        rel = str(relative_path(op["relative"]))
        relative_path(op["source"])
        if op["method"] not in ("merge", "overwrite"):
            raise ValueError("Unsupported file operation")
        if op["volume"] == "data":
            name = Path(rel).name
            if rel != f"Library/Extensions/{name}" or name not in KEXT_NAMES:
                raise ValueError("Data write outside the five Kepler extensions")
            kexts.add(name)
        elif op["volume"] != "system" or not rel.startswith(SYSTEM_PREFIXES):
            raise ValueError("System write outside graphics payload directories")
        elif rel.endswith(".kext"):
            raise ValueError("Offline Kepler extensions must use the prepared AuxKC")
    if kexts != KEXT_NAMES:
        raise ValueError("Incomplete Kepler extension set")


def validate_cache_metadata(text: str, boot_uuid: str, system_uuid: str) -> None:
    for kind, uuid in (("boot kernel", boot_uuid), ("system kext", system_uuid)):
        if f"Linked against {kind} collection UUID: {uuid}" not in text:
            raise ValueError(f"AuxKC does not reference the target {kind} collection")
    required = (
        "com.apple.GeForce", "com.apple.nvidia.driver.NVDAGK100Hal",
        "com.apple.nvidia.driver.NVDAResman", "com.apple.nvidia.NVDAStartup",
        "com.apple.nvidia.driver.NVDAGF100Hal",
    )
    if not all(identifier + "\t" in text for identifier in required):
        raise ValueError("AuxKC is missing a required NVIDIA extension")


def effective_payload_files(base: Path, operations: list[dict]) -> dict:
    """Resolve ordered merges before verification; later source files win."""
    expected = {}
    for op in operations:
        relative = relative_path(op["relative"])
        source = contained_path(base, op["source"])
        if op["method"] == "overwrite":
            expected = {key: value for key, value in expected.items()
                        if key[0] != op["volume"] or not key[1].is_relative_to(relative)}
        files = [source] if source.is_file() else [
            path for path in source.rglob("*") if path.is_file() and not path.is_symlink()
        ]
        for path in files:
            destination = relative if source.is_file() else relative / path.relative_to(source)
            expected[(op["volume"], destination)] = path
    return expected


class OfflineTahoeRecovery:
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path.resolve()
        self.base = self.manifest_path.parent
        self.manifest = json.loads(self.manifest_path.read_text())
        self.backup = self.base / "before-offline-patch"
        self.mount = self.base / "target-system-mount"
        self.journal = self.base / "offline-operations.jsonl"

    def run(self, args: list[str]) -> bytes:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with self.journal.open("a") as stream:
            stream.write(json.dumps({"command": args, "returncode": result.returncode,
                                     "output": result.stdout.decode(errors="replace")}) + "\n")
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace"))
        return result.stdout

    def info(self, value: str) -> dict:
        return plistlib.loads(self.run(["/usr/sbin/diskutil", "info", "-plist", value]))

    def check(self) -> dict:
        validate_manifest(self.manifest)
        host = self.info("/")
        system = self.info(self.manifest["target_system_uuid"])
        data = self.info(self.manifest["target_data_uuid"])
        validate_identities(host, system, data, self.manifest)
        self.system, self.data = Path(system["MountPoint"]), Path(data["MountPoint"])
        version = plistlib.loads((self.system / "System/Library/CoreServices/SystemVersion.plist").read_bytes())
        if version["ProductBuildVersion"] != self.manifest["target_build"]:
            raise ValueError("Target OS build changed")
        if sha256(self.base / "patchset.json") != self.manifest["patchset_sha256"]:
            raise ValueError("Patchset metadata changed after review")
        meta = self.system / "System/Library/CoreServices/OpenCore-Legacy-Patcher.plist"
        if meta.exists():
            raise ValueError("Target already has patch metadata; inspect before retrying")
        for relative, digest in self.manifest["payload_hashes"].items():
            path = contained_path(self.base / "payload", relative)
            if path.is_symlink() or sha256(path) != digest:
                raise ValueError(f"Payload hash mismatch: {relative}")
        for relative, link in self.manifest["payload_symlinks"].items():
            path = self.base / "payload" / relative_path(relative)
            if os.readlink(path) != link or not path.resolve().is_relative_to((self.base / "payload").resolve()):
                raise ValueError(f"Unsafe or changed payload symlink: {relative}")
        aux = self.base / "AuxiliaryKernelExtensions.kc"
        if sha256(aux) != self.manifest["aux_sha256"]:
            raise ValueError("Prepared auxiliary cache changed")
        for name, digest in self.manifest["target_kc_hashes"].items():
            if sha256(self.system / "System/Library/KernelCollections" / name) != digest:
                raise ValueError("Target kernel collections changed after the isolated build")
        inspect = self.run(["/usr/bin/kmutil", "inspect", "--no-variant-extension",
                            "--auxiliary-path", str(aux), "--show-collection-metadata", "--show-extension-info"]).decode()
        validate_cache_metadata(inspect, self.manifest["boot_kc_uuid"], self.manifest["system_kc_uuid"])
        for op in self.manifest["operations"]:
            root = self.system if op["volume"] == "system" else self.data
            if not contained_path(root, op["relative"]).parent.is_dir():
                raise ValueError(f"Missing destination parent: {op['relative']}")
            contained_path(self.base, op["source"])
        snapshots = plistlib.loads(self.run(["/usr/sbin/diskutil", "apfs", "listSnapshots",
                                            system["DeviceIdentifier"], "-plist"]))
        if self.manifest["original_snapshot_uuid"] not in str(snapshots):
            raise ValueError("Original Tahoe snapshot is not available for rollback")
        self.snapshots_before = snapshots
        self.device = system["DeviceIdentifier"]
        self.host_identity = host
        return {"target_build": version["ProductBuildVersion"], "operations": len(self.manifest["operations"]),
                "cache_bindings_verified": True, "original_snapshot_available": True,
                "system_uuid": system["VolumeUUID"], "data_uuid": data["VolumeUUID"]}

    def protected_hashes(self) -> dict:
        files = [Path("/Library/Extensions/GeForce.kext/Contents/MacOS/GeForce"),
                 Path("/Library/KernelCollections/AuxiliaryKernelExtensions.kc"),
                 Path("/System/Library/CoreServices/OpenCore-Legacy-Patcher.plist")]
        return {str(path): sha256(path) for path in files}

    def mount_target(self) -> None:
        self.mount.mkdir(mode=0o700, exist_ok=True)
        if self.mount.is_symlink() or any(self.mount.iterdir()):
            raise ValueError("Temporary mount point must be an empty real directory")
        self.run(["/usr/sbin/diskutil", "unmount", self.device])
        self.run(["/sbin/mount_apfs", "-o", "nobrowse", f"/dev/{self.device}", str(self.mount)])
        self.system = self.mount
        info = self.info(str(self.mount))
        if info.get("VolumeUUID") != self.manifest["target_system_uuid"] or not info.get("Writable"):
            raise ValueError("Writable mount is not the intended Tahoe System volume")

    def copy_item(self, source: Path, dest: Path, merge: bool = False) -> None:
        if not dest.parent.is_dir():
            raise ValueError(f"Expected destination directory is absent: {dest.parent}")
        if merge:
            self.run(["/usr/bin/rsync", "-ria", str(source) + "/", str(dest) + "/"])
        else:
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)
            self.run(["/usr/bin/ditto", str(source), str(dest)])
        # Physical ownership walk: never follow a framework link into another volume.
        entries = [dest]
        if dest.is_dir() and not dest.is_symlink():
            entries.extend(dest.rglob("*"))
        for path in entries:
            os.lchown(path, 0, 0)
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644)

    def prepare_backup(self) -> dict:
        if self.backup.exists():
            previous = json.loads((self.base / "offline-apply-result.json").read_text())
            if previous.get("status") != "failed" or previous.get("rollback") != "original_data_restored_and_sealed_snapshot_selected":
                raise ValueError("Previous attempt did not confirm rollback; refusing to retry")
            state = json.loads((self.backup / "state.json").read_text())
            if state["original_snapshot_uuid"] != self.manifest["original_snapshot_uuid"]:
                raise ValueError("Original backup belongs to a different snapshot")
            for item in state["data_files"]:
                current = contained_path(self.data, item["relative"])
                saved = self.backup / "data" / item["relative"]
                if not item["existed"]:
                    if current.exists() or current.is_symlink():
                        raise ValueError("Data changed since rollback; do not overwrite it")
                elif saved.is_file():
                    if sha256(current) != sha256(saved):
                        raise ValueError("Restored Data file differs from the original backup")
                else:
                    raise ValueError("Directory backup needs manual review before retry")
            # Retain the first failure receipt and the original backup unchanged.
            failure = self.base / "offline-first-failure.json"
            if not failure.exists():
                failure.write_text(json.dumps(previous, indent=2))
            return state
        self.backup.mkdir(mode=0o700)
        state = {"data_files": [], "original_snapshot_uuid": self.manifest["original_snapshot_uuid"]}
        items = [f"Library/Extensions/{name}" for name in sorted(KEXT_NAMES)]
        items.append("Library/KernelCollections/AuxiliaryKernelExtensions.kc")
        policy = "private/var/db/SystemPolicyConfiguration/"
        items.extend(policy + name for name in ("KextPolicy", "KextPolicy-shm", "KextPolicy-wal"))
        for relative in items:
            source = contained_path(self.data, relative)
            exists = source.exists()
            state["data_files"].append({"relative": relative, "existed": exists})
            if exists:
                dest = self.backup / "data" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.run(["/usr/bin/ditto", str(source), str(dest)])
        (self.backup / "state.json").write_text(json.dumps(state, indent=2))
        return state

    def restore_data(self, state: dict) -> None:
        for item in state["data_files"]:
            dest = contained_path(self.data, item["relative"])
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)
            if item["existed"]:
                self.run(["/usr/bin/ditto", str(self.backup / "data" / item["relative"]), str(dest)])

    def apply(self) -> dict:
        if os.geteuid() != 0:
            raise PermissionError("Apply requires local administrator authentication")
        preflight = self.check()
        protected = self.protected_hashes()
        state = self.prepare_backup()
        result = {"time": datetime.datetime.now().astimezone().isoformat(), "preflight": preflight,
                  "efi_changed": False, "boot_default_changed": False}
        modified = False
        try:
            self.mount_target()
            # Validate the writable mount against the independently resolved Data member.
            validate_identities(self.host_identity, self.info(str(self.system)), self.info(str(self.data)), self.manifest)
            modified = True
            for op in self.manifest["operations"]:
                root = self.system if op["volume"] == "system" else self.data
                self.copy_item(contained_path(self.base, op["source"]), contained_path(root, op["relative"]), op["method"] == "merge")
            self.copy_item(self.base / "AuxiliaryKernelExtensions.kc",
                           self.data / "Library/KernelCollections/AuxiliaryKernelExtensions.kc")
            # Offline equivalent of OCLP's AuxKC policy invalidation, scoped to Tahoe Data.
            # No host processes are killed and ExecPolicy is never changed.
            for name in ("KextPolicy", "KextPolicy-shm", "KextPolicy-wal"):
                policy = contained_path(self.data, "private/var/db/SystemPolicyConfiguration/" + name)
                if policy.exists():
                    policy.unlink()
            self.verify_installed()
            patchset = json.loads((self.base / "patchset.json").read_text())
            # Describe actual auxiliary destinations instead of the untransformed source map.
            extensions = patchset["Nvidia Kepler"]["Overwrite System Volume"]["/System/Library/Extensions"]
            moved = {name: extensions.pop(name) for name in list(extensions) if name.endswith(".kext")}
            patchset["Nvidia Kepler"]["Overwrite System Volume"]["/Library/Extensions"] = moved
            metadata = {"OpenCore Legacy Patcher": "v3.0.0 (experimental offline recovery)",
                        "PatcherSupportPkg": "v2.0.3", "Time Patched": datetime.datetime.now().isoformat(),
                        "Commit URL": "https://github.com/ferxalbs/OpenCore-Legacy-Patcher",
                        "Kernel Debug Kit Used": "Not applicable", "Metal Library Used": "Not applicable",
                        "OS Version": "25.6 (25G241)", "Custom Signature": False, **patchset}
            meta = self.system / "System/Library/CoreServices/OpenCore-Legacy-Patcher.plist"
            meta.write_bytes(plistlib.dumps(metadata, sort_keys=False))
            meta.chmod(0o644)
            self.run(["/bin/sync"])
            self.run(["/usr/sbin/bless", "--folder", str(self.system / "System/Library/CoreServices"),
                      "--bootefi", "--create-snapshot"])
            result["snapshots_after"] = self.run(["/usr/sbin/diskutil", "apfs", "listSnapshots", self.device]).decode()
            snapshots = plistlib.loads(self.run(["/usr/sbin/diskutil", "apfs", "listSnapshots", self.device, "-plist"]))
            previous = {entry["SnapshotUUID"] for entry in self.snapshots_before["Snapshots"]}
            created = {entry["SnapshotUUID"] for entry in snapshots["Snapshots"]} - previous
            if not created:
                raise RuntimeError("No new Tahoe snapshot appeared after bless")
            result["created_snapshot_uuids"] = sorted(created)
            result["bless_info"] = self.run(["/usr/sbin/bless", "--info", "--plist", str(self.system)]).decode()
            if self.protected_hashes() != protected:
                raise RuntimeError("Protected host files changed during the operation; inspect before booting")
            result.update(status="tahoe_offline_patched_reboot_required", sequoia_protected_files_unchanged=True,
                          installed_payload_verified=True, runtime_verified=False)
        except Exception as error:
            result.update(status="failed", error=str(error))
            if modified:
                try:
                    self.restore_data(state)
                    self.run(["/usr/sbin/bless", "--mount", str(self.system), "--bootefi", "--last-sealed-snapshot"])
                    result["rollback"] = "original_data_restored_and_sealed_snapshot_selected"
                except Exception as rollback:
                    result["rollback_error"] = str(rollback)
            raise
        finally:
            if self.system == self.mount:
                try:
                    self.run(["/bin/sync"])
                    self.run(["/sbin/umount", str(self.mount)])
                    self.run(["/usr/sbin/diskutil", "mount", "readOnly", self.device])
                except Exception as error:
                    result["remount_error"] = str(error)
            (self.base / "offline-apply-result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        return result

    def restore(self) -> dict:
        """Select the original sealed Tahoe snapshot and restore its Data changes."""
        if os.geteuid() != 0:
            raise PermissionError("Restore requires local administrator authentication")
        host = self.info("/")
        system = self.info(self.manifest["target_system_uuid"])
        data = self.info(self.manifest["target_data_uuid"])
        validate_identities(host, system, data, self.manifest)
        self.device = system["DeviceIdentifier"]
        self.system, self.data = Path(system["MountPoint"]), Path(data["MountPoint"])
        state = json.loads((self.backup / "state.json").read_text())
        if state["original_snapshot_uuid"] != self.manifest["original_snapshot_uuid"]:
            raise ValueError("Rollback snapshot does not match the reviewed target")
        snapshots = self.run(["/usr/sbin/diskutil", "apfs", "listSnapshots", self.device]).decode()
        if state["original_snapshot_uuid"] not in snapshots:
            raise ValueError("Original sealed snapshot is missing; do not guess a replacement")
        protected = self.protected_hashes()
        try:
            self.mount_target()
            self.restore_data(state)
            self.run(["/usr/sbin/bless", "--mount", str(self.system), "--bootefi", "--last-sealed-snapshot"])
            if self.protected_hashes() != protected:
                raise RuntimeError("Protected host files changed; review the journal")
            result = {"status": "tahoe_original_data_and_sealed_snapshot_restored",
                      "sequoia_protected_files_unchanged": True, "efi_changed": False}
            (self.base / "offline-restore-result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
            return result
        finally:
            if self.system == self.mount:
                self.run(["/sbin/umount", str(self.mount)])
                self.run(["/usr/sbin/diskutil", "mount", "readOnly", self.device])

    def verify_installed(self) -> None:
        expected = effective_payload_files(self.base, self.manifest["operations"])
        for (volume, relative), original in expected.items():
            root = self.system if volume == "system" else self.data
            installed = contained_path(root, str(relative))
            if sha256(original) != sha256(installed):
                raise ValueError(f"Installed payload differs: {installed}")
        if sha256(self.data / "Library/KernelCollections/AuxiliaryKernelExtensions.kc") != self.manifest["aux_sha256"]:
            raise ValueError("Installed AuxKC differs from the tested artifact")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    recovery = OfflineTahoeRecovery(args.manifest)
    if args.check:
        print(json.dumps(recovery.check(), indent=2))
    elif args.restore:
        recovery.restore()
    else:
        recovery.apply()


if __name__ == "__main__":
    main()
