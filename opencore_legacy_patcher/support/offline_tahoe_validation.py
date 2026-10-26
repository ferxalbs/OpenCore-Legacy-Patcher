"""Read-only isolation checks for the experimental offline Tahoe recovery."""

import copy
from pathlib import Path
import tempfile

from ..sys_patch.offline_tahoe import (
    KEXT_NAMES, contained_path, relative_path, validate_cache_metadata,
    validate_identities, validate_manifest,
)


def validate_offline_tahoe_recovery() -> None:
    """Reject host writes, mixed volume groups, escaping paths and foreign KCs."""
    manifest = {
        "target_build": "25G241", "target_group_uuid": "TAHOE-GROUP",
        "target_system_uuid": "TAHOE-SYSTEM", "target_data_uuid": "TAHOE-DATA",
        "operations": [{"volume": "data", "method": "overwrite",
                        "relative": f"Library/Extensions/{name}",
                        "source": f"payload/{name}"} for name in KEXT_NAMES],
    }
    host = {"APFSVolumeGroupID": "SEQUOIA-GROUP"}
    system = {"APFSVolumeGroupID": "TAHOE-GROUP", "VolumeUUID": "TAHOE-SYSTEM",
              "APFSContainerReference": "disk1", "MountPoint": "/Volumes/Tahoe"}
    data = {**system, "VolumeUUID": "TAHOE-DATA", "MountPoint": "/Volumes/Tahoe-Data"}

    def must_reject(function, *args):
        try:
            function(*args)
        except ValueError:
            return
        raise AssertionError(f"Offline recovery accepted an unsafe input in {function.__name__}")

    validate_manifest(manifest)
    validate_identities(host, system, data, manifest)
    must_reject(validate_identities, {"APFSVolumeGroupID": "TAHOE-GROUP"}, system, data, manifest)
    must_reject(validate_identities, host, {**system, "MountPoint": "/"}, data, manifest)
    must_reject(validate_identities, host, system, {**data, "APFSVolumeGroupID": "SEQUOIA-GROUP"}, manifest)
    must_reject(validate_identities, host, system, {**data, "VolumeUUID": "TAHOE-SYSTEM"}, manifest)
    must_reject(validate_identities, host, system, {**data, "APFSContainerReference": "disk9"}, manifest)
    for path in ("/Library/Extensions", "../Library", "System/../Library", ""):
        must_reject(relative_path, path)
    for field, value in (("relative", "private/var/db/ExecPolicy"), ("volume", "host"), ("method", "execute")):
        bad = copy.deepcopy(manifest)
        bad["operations"][0][field] = value
        must_reject(validate_manifest, bad)
    bad = copy.deepcopy(manifest)
    bad["target_build"] = "24G720"
    must_reject(validate_manifest, bad)
    bad = copy.deepcopy(manifest)
    bad["operations"].pop()
    must_reject(validate_manifest, bad)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "target"
        root.mkdir()
        (root / "escape").symlink_to(root.parent, target_is_directory=True)
        must_reject(contained_path, root, "escape/another-volume")
        assert contained_path(root, "System/Library/Metal") == root / "System/Library/Metal"

    identifiers = ["com.apple.GeForce", "com.apple.nvidia.driver.NVDAGK100Hal",
                   "com.apple.nvidia.driver.NVDAResman", "com.apple.nvidia.NVDAStartup",
                   "com.apple.nvidia.driver.NVDAGF100Hal"]
    metadata = ("Linked against boot kernel collection UUID: TAHOE-BOOT\n"
                "Linked against system kext collection UUID: TAHOE-SYS\n"
                + "\n".join(identifier + "\t16.0.0" for identifier in identifiers))
    validate_cache_metadata(metadata, "TAHOE-BOOT", "TAHOE-SYS")
    must_reject(validate_cache_metadata, metadata, "SEQUOIA-BOOT", "TAHOE-SYS")
    must_reject(validate_cache_metadata, metadata, "TAHOE-BOOT", "SEQUOIA-SYS")
    must_reject(validate_cache_metadata, metadata.replace("com.apple.GeForce\t", "missing\t"), "TAHOE-BOOT", "TAHOE-SYS")
