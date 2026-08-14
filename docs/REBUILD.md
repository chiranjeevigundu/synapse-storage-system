# Rebuilding the Mac Mini (Linux) node

Wiping and reinstalling the 24/7 compute node. Follow top to bottom.

Phase 0 is the only irreversible part. Everything after it can be retried.

---

## Read this first: two things that bite before you start

**Cancel the queued deploy before you register any runner.** A run has been queued since
2026-08-13T22:39. GitHub does not discard a queued job when its runner deregisters — it
holds it and hands it to the *first runner that matches the labels*. `deploy.yml` uses a
bare `runs-on: self-hosted` with no extra labels, so **any** runner you register, even a
throwaway test one, claims that job instantly. It then `rsync -av --delete`s a stale
commit's tree over the deploy directory and rebuilds from it — on a fresh OS, before you
have verified the NAS mount. Cancel it, confirm the Actions tab shows zero queued runs,
then register.

**A self-hosted runner on a public repo is remote code execution on this box.** A fork
does not need to edit `deploy.yml`; it adds a *new* workflow file with
`on: pull_request` and `runs-on: self-hosted`, and its shell runs as `linuxuser` on your
Mac Mini. The only barrier is the "Approve and run" button — and that barrier disappears
permanently once a contributor has one merged PR. A benign typo fix today buys unlimited
unapproved runner access tomorrow. Decide before re-registering: make the repo private,
switch to a pull-based deploy, or accept the risk knowingly.

---

## Phase 0 — capture, while the box is still alive

Nothing here is recoverable after the wipe.

### 0.1 Prove the NAS is actually mounted

If `/mnt/nas_data` is a plain local directory rather than a mount, you are about to back
up the dying disk onto the dying disk. Abort and investigate if this fails.

```bash
mountpoint -q /mnt/nas_data || { echo 'ABORT: not a mountpoint'; exit 1; }
export BK=/mnt/nas_data/05_SYSTEM/preflight_$(date +%Y-%m-%d_%H-%M-%S)
mkdir -p "$BK" && df -h /mnt/nas_data | tee "$BK/df.txt"
```

### 0.2 The NAS mount configuration — the highest-value thing on the dying disk

Nothing in this repo records how `/mnt/nas_data` is mounted. Not the compose file (it
bind-mounts a path it assumes exists), not `deploy/setup_env.sh` (it only mkdirs *inside*
the path). The fstab line, filesystem type, mount options and credentials path exist
**only on this box**.

```bash
cp /etc/fstab "$BK/fstab"
findmnt -T /mnt/nas_data -o SOURCE,TARGET,FSTYPE,OPTIONS | tee "$BK/nas_mount.txt"
grep -n nas_data /etc/fstab | tee -a "$BK/nas_mount.txt"
systemctl list-units --type=mount --type=automount --all --no-pager >> "$BK/nas_mount.txt"
cp /etc/systemd/system/*.mount /etc/systemd/system/*.automount "$BK/" 2>/dev/null
grep -oP 'credentials=\S+' /etc/fstab | tee "$BK/CREDS_PATH_copy_offline.txt"
```

The credentials file holds your NAS password in plaintext. Record its *path* here; copy
the file itself to encrypted offline media, **not** onto the share it unlocks.

### 0.3 Network identity — three things fail silently if it changes

```bash
ip -br addr | tee "$BK/ip_addr.txt"
for c in $(nmcli -g NAME con show 2>/dev/null); do
  echo "### $c"; nmcli con show "$c" | grep -Ei 'ipv4.method|ipv4.addresses|ipv4.gateway|ipv4.dns'
done | tee "$BK/nmcli.txt"
cat /etc/netplan/*.yaml > "$BK/netplan.txt" 2>/dev/null
tailscale status --json > "$BK/tailscale_status.json" 2>&1
tailscale ip -4 | tee "$BK/tailscale_ip.txt"
hostname | tee "$BK/hostname.txt"
```

- **`192.168.12.37` is hardcoded** in `client/windows_sentinel.ps1:2`. Those Sentinels run
  as Hidden scheduled tasks: on a new address they loop every 2 seconds forever, writing
  failures to a console nobody sees, leaving files in `C:\NAS_Outbox`. No alert. Find out
  whether .37 is static or a DHCP reservation and preserve it, or you touch every client
  by hand.
- **Tailscale's node key** lives in `/var/lib/tailscale/tailscaled.state`. Wipe it and the
  box rejoins as a *new* node; the old one keeps the hostname, so MagicDNS gives the new
  one a `-1` suffix and possibly a different `100.x`. Any iOS Shortcut with the old IP
  fails as a toast the user learns to ignore.

### 0.4 Grafana — already dying on every deploy

Grafana has no volume, so its SQLite DB is in the container's writable layer, and
`deploy.yml:41` runs `docker compose down`. Every deploy has already wiped your
dashboards. Anything built since the last deploy exists now and dies at the wipe.

```bash
docker cp synapse_grafana:/var/lib/grafana/grafana.db "$BK/grafana.db"
curl -s -u admin:admin 'http://localhost:3000/api/search?type=dash-db' > "$BK/dashlist.json"
curl -s -u admin:admin http://localhost:3000/api/datasources > "$BK/datasources.json"
```

If you ever changed the admin password in the UI, it lives only in that DB —
`GF_SECURITY_ADMIN_PASSWORD` applies at first-init only, so the rebuild silently reverts
to `admin`/`admin`.

### 0.5 Ledger, logs, and image digests

```bash
cp /mnt/nas_data/ledger.json "$BK/ledger.json"
python3 -c "import json;d=json.load(open('/mnt/nas_data/ledger.json'));print('entries:',len(d.get('entries',d.get('hashes',[]))))" | tee "$BK/ledger_count_before.txt"
for c in $(docker ps -a --format '{{.Names}}'); do docker logs "$c" > "$BK/log_$c.txt" 2>&1; done
docker images --digests --format '{{.Repository}}:{{.Tag}}@{{.Digest}}' | tee "$BK/image_digests.txt"
echo "nas-sentinel $(date -Is)" > /mnt/nas_data/05_SYSTEM/.nas_sentinel
```

**Every image tag is unpinned** (`kong:3.9`, `prom/prometheus`, `grafana/grafana-oss`,
`ollama/ollama:latest`). A rebuild will not give you the same versions. Capture the
digests so you can pin or at least diagnose a behaviour change.

The `.nas_sentinel` file is the post-rebuild proof that you are looking at the real NAS
and not a local directory Docker invented.

### 0.6 Do not restore the ledger from `src/ledger.json`

The live ledger is `/mnt/nas_data/ledger.json` and it survives on the NAS. The tracked
`src/ledger.json` is a dead 4-entry legacy artifact. Pointing `LEDGER_PATH` at it would
silently reset duplicate detection to 4 hashes.

---

## Phase 1 — fresh OS

**Before wiping**, identify the exact Mac Mini model and boot mechanism (Intel vs Apple
Silicon changes everything about what Linux you can install and how it boots). That is
discoverable only on the machine.

The account **must be named `linuxuser` and be UID 1000**. `deploy.yml` hardcodes
`/home/linuxuser/...` and `setup_env.sh` chowns to `1000:1000`. On a normal Ubuntu install
the first account is UID 1000 automatically — verify it.

```bash
id linuxuser        # expect uid=1000(linuxuser) gid=1000(linuxuser)
```

Set the account password to match the existing `SSH_PASSWORD` GitHub secret, or update the
secret immediately. `deploy.yml` uses `sudo -S` three times; if it fails it can die
*after* `docker compose down` and before `up`, leaving the stack down.

Base packages a minimal install lacks: `rsync`, `curl`, `git`, plus `cifs-utils` (SMB) or
`nfs-common` (NFS). Set timezone and NTP — every ledger timestamp and the weekly integrity
audit depend on the clock.

Install **Docker CE from Docker's own apt repo**, not Ubuntu's `docker.io` package, which
does not ship the compose v2 plugin the workflow calls as `docker compose`.

---

## Phase 2 — the NAS mount, and the trap

### 2.1 The boot-order trap

This is the highest-consequence failure in the rebuild, and it is completely silent.

All six services use `restart: unless-stopped`, so dockerd starts them the moment it
starts. Nothing orders dockerd after the network mount. When Docker meets a bind mount
whose source does not exist, **it creates the directory** rather than failing. So on a boot
where the NAS is slow or unreachable:

1. Docker creates `/mnt/nas_data` on the **root filesystem**
2. An upload arrives; `ingest_api` mkdirs `00_INGEST` locally, writes the file, returns
   **200 OK**. The phone says "Upload to Universe Complete!" The file is on the wrong disk.
3. Ollama sees an empty model dir and re-pulls several GB onto the root disk
4. The NAS finally mounts *over* that directory — everything written is now shadowed:
   invisible, still consuming root-disk space, unreachable

Worse, `src/utils.py:39` hardcodes `base_nas = Path("/mnt/nas_data")`, ignoring
`NAS_BASE_PATH`, so you cannot redirect writes by config.

### 2.2 Two defences, apply both

```bash
# 1. dockerd must not start without the mount
sudo systemctl edit docker.service
#   [Unit]
#   RequiresMountsFor=/mnt/nas_data

# 2. the bare mountpoint is physically unwritable when nothing is mounted
sudo umount /mnt/nas_data
sudo chattr +i /mnt/nas_data
lsattr -d /mnt/nas_data
sudo mount -a
```

The immutable bit means a manual `docker compose up` with the NAS detached fails **loudly**
with EPERM instead of silently writing to the SSD. Mounting over an immutable directory
works normally, so it costs nothing at runtime.

`_netdev` in fstab only works if a wait-online unit is actually enabled — verify
`systemd-networkd-wait-online` or the NetworkManager equivalent is active.

### 2.3 Fix `setup_env.sh` before the first deploy

It has no `set -e` and no mount guard. Line 7 mkdirs into a possibly-unmounted path and
reports success. Line 13 runs `chown -R 1000:1000 /mnt/nas_data` — **recursively across
your entire NAS, on every push to main**. On CIFS it fails silently; on
`no_root_squash` NFS it succeeds and rewrites ownership of every file on the array, hours
per deploy, clobbering intentional per-directory ownership.

Add a fail-fast guard at minimum:

```bash
set -euo pipefail
mountpoint -q /mnt/nas_data || { echo "NAS not mounted, refusing"; exit 1; }
test -f /mnt/nas_data/05_SYSTEM/.nas_sentinel || { echo "sentinel missing"; exit 1; }
```

It also never creates `/mnt/nas_data/ollama` or `05_SYSTEM/Audit_Reports`.

---

## Phase 3 — fix these while you are already here

Free to do now, painful later.

### Persistence for Prometheus and Grafana

```yaml
  prometheus:
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus          # add

  grafana:
    volumes:
      - grafana_data:/var/lib/grafana        # add
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?set me}

volumes:                                     # new top-level block
  prometheus_data:
  grafana_data:
```

`.antigravity/skills/monitoring.md` describes generating "Weekly Reliability Reports" from
Prometheus. Without a data volume there is no week of history to report on.

### Rotate the API key — it is in FOUR files, not two

`super_secret_homelab_key` appears in `deploy.yml:26`, `.env.example:4`,
**`src/config.py:5`** (as the default, so the API accepts it even with no `.env` at all),
and **`config/kong.yml:21`** (the Kong consumer credential). It is the only auth on the
ingest API, and Kong publishes ports 80 and 443.

```bash
gh secret set API_KEY --repo chiranjeevigundu/synapse-storage-system
```

Then `deploy.yml` → `echo "API_KEY=${{ secrets.API_KEY }}" > .env`, and remove the default
from `config.py` so a missing value fails loudly instead of falling back to the published
one. Deleting it from the working tree does **not** remove it from commit history — the old
value is burned permanently either way.

Rotation breaks every Windows Sentinel and the iOS Shortcut simultaneously. The wipe is
the natural window for that.

---

## Phase 4 — verify before you trust it

In order. Do not proceed past a failure.

```bash
mountpoint -q /mnt/nas_data && echo "mounted"
test -f /mnt/nas_data/05_SYSTEM/.nas_sentinel && echo "REAL NAS confirmed"
python3 -c "import json;d=json.load(open('/mnt/nas_data/ledger.json'));print('entries:',len(d.get('entries',d.get('hashes',[]))))"
```

Compare that ledger count against `ledger_count_before.txt`. **A sudden drop to 0 or 4
means you are looking at a fresh local file, not the NAS.**

Then bring the stack up **manually once** from the correct directory before letting CI
touch it, confirm all six containers are healthy, and only then re-register the runner and
let a deploy run.
