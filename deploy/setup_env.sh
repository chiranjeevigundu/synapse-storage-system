#!/bin/bash
# Initialise the NAS directory structure for the containers.
#
# Two things this script used to get wrong, both silent:
#
# 1. No mount guard. If /mnt/nas_data was not mounted, `mkdir -p` created the tree
#    on the host's internal SSD and reported success. Docker then bind-mounted that
#    local directory, uploads returned 200 OK, and files landed on the wrong disk —
#    until the NAS mounted over the top and shadowed them. That is not theoretical:
#    it is exactly what happened when the NAS moved to a new address and 6.7 GB of
#    model data ended up stranded on the boot drive.
#
# 2. Recursive chown/chmod across the entire share, on every push to main. On CIFS
#    it fails silently because ownership comes from the uid= mount option; on NFS
#    without root_squash it succeeds and rewrites permissions on every file in a
#    14 TB archive, clobbering any intentional per-directory ownership.
#
# The mount is now the authority on ownership. This script only creates the
# directories the containers expect, and refuses to run if the NAS is absent.

set -euo pipefail

NAS_ROOT="${NAS_BASE_PATH:-/mnt/nas_data}"

echo "Initializing Synapse Storage System Environment..."

if ! mountpoint -q "$NAS_ROOT"; then
    echo "FATAL: $NAS_ROOT is not a mountpoint — the NAS is not mounted." >&2
    echo "       Refusing to create directories on the local disk." >&2
    echo "       Check: findmnt -T $NAS_ROOT   and   systemctl status mnt-nas_data.automount" >&2
    exit 1
fi

# Directories the compose file and the application expect to exist. 05_SYSTEM and
# the audit directory were previously missing here, so the integrity auditor had
# nowhere to write its corruption reports.
mkdir -p "$NAS_ROOT/00_INGEST"
mkdir -p "$NAS_ROOT/05_SYSTEM/Audit_Reports"
mkdir -p "$NAS_ROOT/ollama"

# Ownership is set by the mount (uid=/gid= for CIFS), not here. If a future backend
# needs it applied explicitly, scope it to these directories rather than -R across
# the whole archive.

echo "Environment setup complete. NAS verified mounted at $NAS_ROOT"
