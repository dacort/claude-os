---
profile: medium
priority: high
status: completed
created: "2026-03-15T19:35:00Z"
completed: "2026-03-15T20:05:00Z"
---

# Validate Talos Tailscale Extension Setup (dry-run)

## Results

All steps passed. No changes were applied to the node.

---

### Step 1: Funnel Connectivity ✅

```
curl -s https://damons-macbook-air.tail1c8fc.ts.net/test.txt
→ hello from the funnel 🐙
```

---

### Step 2: Talosconfig ✅

Fetched successfully. File was 8 lines. Deleted after use.

---

### Step 3: Talos API Access ✅

```
Client:  v1.12.5 (talosctl-linux-amd64 from latest release)
Server:  v1.12.4 @ 192.168.7.199 (RBAC enabled)
```

Existing extensions: none installed (empty list returned).

---

### Step 4: Auth Key + Config Patch ✅

Auth key fetched (63 bytes). Patch built with:

- Extension image: `ghcr.io/siderolabs/tailscale:1.94.1`
- File: `/var/etc/tailscale/auth.env` (permissions: 0o600, op: create)
- Contents: TS_AUTHKEY, TS_ROUTES=10.244.0.0/16,10.96.0.0/12, TS_EXTRA_ARGS=--advertise-tags=tag:kubernetes --hostname=sealab, TS_ACCEPT_DNS=false

---

### Step 5: Dry-Run ✅

```
patched MachineConfigs.config.talos.dev/v1alpha1 at the node 192.168.7.199
Dry run summary:
Applied configuration with a reboot (skipped in dry-run).
Config diff:

--- a
+++ b
@@ -18,8 +18,19 @@
     install:
         disk: /dev/nvme0n1
         image: ghcr.io/siderolabs/installer:v1.12.4
+        extensions:
+            - image: ghcr.io/siderolabs/tailscale:1.94.1
         wipe: false
         grubUseUKICmdline: true
+    files:
+        - content: |
+            TS_AUTHKEY=<redacted>
+            TS_ROUTES=10.244.0.0/16,10.96.0.0/12
+            TS_EXTRA_ARGS=--advertise-tags=tag:kubernetes --hostname=sealab
+            TS_ACCEPT_DNS=false
+          permissions: 0o600
+          path: /var/etc/tailscale/auth.env
+          op: create
     features:
         diskQuotaSupport: true
         kubePrism:
```

Applying this config **requires a node reboot** (extension installs always do).

---

### Step 6: Correct Extension Image Tag ✅

Image: **`ghcr.io/siderolabs/tailscale:1.94.1`**

Source: `siderolabs/extensions` CHANGELOG at tag `v1.12.4`. Tailscale `1.94.1` was
introduced in extensions `v1.12.3` and carried forward unchanged to `v1.12.4`.
The `v1.12.4` release focused on Intel ucode, NVIDIA LTS, bird2, gvisor, and
cloudflared updates — not tailscale.

---

### Security Cleanup ✅

- `/tmp/talosconfig` — deleted
- `/tmp/ts-authkey` — deleted
- `/tmp/tailscale-patch.yaml` — deleted
- No secrets committed to repository

---

## Ready to Apply

When dacort is ready to actually install the extension:

```bash
# Generate upgrade command using the correct installer image with the extension baked in
# DO NOT use talosctl patch machineconfig without --dry-run until ready
talosctl --talosconfig ~/.talos/config -n 192.168.7.199 \
  upgrade --image ghcr.io/siderolabs/installer:v1.12.4 \
  --with-extensions ghcr.io/siderolabs/tailscale:1.94.1
```

Or use `talosctl patch machineconfig` (without `--dry-run`) after verifying the
auth key is still valid.
