---
profile: medium
priority: high
status: pending
created: "2026-03-15T20:10:00Z"
---

# Apply Talos Tailscale Extension (FOR REAL)

## Description

This task applies the Tailscale extension to our Talos node. This WILL reboot the node, which means this worker will die mid-task. That is expected.

The temporary file server at `https://damons-macbook-air.tail1c8fc.ts.net/` has the credentials needed.

### Step 1: Fetch credentials
```bash
curl -s https://damons-macbook-air.tail1c8fc.ts.net/talosconfig -o /tmp/talosconfig
curl -s https://damons-macbook-air.tail1c8fc.ts.net/authkey -o /tmp/ts-authkey
```

### Step 2: Verify API access (sanity check)
```bash
curl -sL https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-amd64 -o /tmp/talosctl && chmod +x /tmp/talosctl
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 version
```
If this fails, STOP. Do not proceed.

### Step 3: Build and apply the config patch

Create `/tmp/tailscale-patch.yaml`:
```yaml
machine:
  install:
    extensions:
      - image: ghcr.io/siderolabs/tailscale:1.94.1
  files:
    - content: |
        TS_AUTHKEY=<contents of /tmp/ts-authkey>
        TS_ROUTES=10.244.0.0/16,10.96.0.0/12
        TS_EXTRA_ARGS=--advertise-tags=tag:kubernetes --hostname=sealab
        TS_ACCEPT_DNS=false
      permissions: 0o600
      path: /var/etc/tailscale/auth.env
      op: create
```

Apply it FOR REAL (no --dry-run):
```bash
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 patch machineconfig --patch-file /tmp/tailscale-patch.yaml
```

### Step 4: Trigger the upgrade

The extension won't actually load until the node reboots with an image that includes it. Trigger:
```bash
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 upgrade --image factory.talos.dev/installer/376567988ad370138ad8b2698212367b8edcb69b5fd68c80be1f2ec7d603b4ba:v1.12.4
```

Note: The schematic ID above is for Talos v1.12.4 + tailscale extension. If that doesn't work, try the Image Factory API to generate the right schematic:
```bash
SCHEMATIC=$(curl -sX POST https://factory.talos.dev/schematics -d '{"customization":{"systemExtensions":{"officialExtensions":["siderolabs/tailscale"]}}}' | jq -r .id)
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 upgrade --image factory.talos.dev/installer/${SCHEMATIC}:v1.12.4
```

### Step 5: Accept death gracefully

The node will reboot. This pod will be terminated. That is success, not failure.

Before triggering the upgrade, write a note to git so we know the command was sent:
```bash
cd /workspace/claude-os
echo "Tailscale config applied and upgrade triggered at $(date -u). Node is rebooting." > tasks/completed/talos-tailscale-apply-status.txt
git add -A && git commit -m "talos-tailscale-apply: config applied, upgrade triggered, node rebooting" && git push
```

Then trigger the upgrade. Godspeed. 🐙

⚠️ SECURITY: Delete /tmp/talosconfig and /tmp/ts-authkey before the git push. Do not commit their contents.
