---
profile: medium
priority: high
status: pending
created: "2026-03-15T19:35:00Z"
---

# Validate Talos Tailscale Extension Setup (dry-run)

## Description

This is a VALIDATION ONLY task — do NOT run `talosctl upgrade` or apply any changes.

A temporary file server is running at `https://damons-macbook-air.tail1c8fc.ts.net/`. It serves files needed for setting up the Tailscale extension on our Talos node. This server will be shut down shortly after this task completes.

### Step 1: Test funnel connectivity
```
curl -s https://damons-macbook-air.tail1c8fc.ts.net/test.txt
```
Expected output: `hello from the funnel 🐙`

### Step 2: Fetch talosconfig credentials
```
curl -s https://damons-macbook-air.tail1c8fc.ts.net/talosconfig -o /tmp/talosconfig
```

### Step 3: Verify Talos API access
Using the fetched talosconfig, verify we can talk to the Talos API:
```
# Download talosctl if not available
curl -sL https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-amd64 -o /tmp/talosctl && chmod +x /tmp/talosctl

/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 version
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 get extensions
```

### Step 4: Fetch auth key and build config patch
```
curl -s https://damons-macbook-air.tail1c8fc.ts.net/authkey -o /tmp/ts-authkey
```

Build a machine config patch that:
1. Adds the Tailscale extension image
2. Creates `/var/etc/tailscale/auth.env` with:
   - TS_AUTHKEY=(contents of /tmp/ts-authkey)
   - TS_ROUTES=10.244.0.0/16,10.96.0.0/12
   - TS_EXTRA_ARGS=--advertise-tags=tag:kubernetes --hostname=sealab
   - TS_ACCEPT_DNS=false

### Step 5: Dry-run the config patch
```
/tmp/talosctl --talosconfig /tmp/talosconfig -n 192.168.7.199 patch machineconfig --dry-run --patch-file /tmp/tailscale-patch.yaml
```

### Step 6: Look up the correct Tailscale extension image
Check https://github.com/siderolabs/extensions for the right image tag compatible with Talos v1.12.4.

### Output
Write a summary of all results (connectivity, API access, dry-run output, correct image tag) back to the task results. Do NOT apply any changes. Do NOT run `talosctl upgrade`.

⚠️ SECURITY: Delete /tmp/talosconfig and /tmp/ts-authkey when done. Do not commit their contents anywhere.
