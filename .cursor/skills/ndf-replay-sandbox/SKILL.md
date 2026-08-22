---
name: ndf-replay-sandbox
description: >-
  Installs and verifies the local Lvm Guest VM used by NDF Workflow Canvas
  Replay (KVM + qemu + guest-image). Use when the user asks to install the
  replay sandbox, Guest VM, qemu/KVM, guest-image, or when Canvas guest-run
  returns environment_blocked / missing image.
---

# NDF Replay Sandbox Install

Default backend is **local KVM** (`guest-run --adapter vm`). CubeSandbox is
optional and MUST NOT be the default. Contract: [[META-015]] / [[META-013]].

Canvas Replay only launches `guest-run`. Prompt labels, worktree, `bwrap`, and
`fake-vm` are not completed replay.

## Agent workflow

Copy and track:

```text
- [ ] 1. guest-probe
- [ ] 2. follow next_actions in order (no extras)
- [ ] 3. guest-probe again until ready=true
- [ ] 4. smoke guest-run
- [ ] 5. report proof; stop if blocked
```

### 1. Probe

From `workspace.repo_root` (or the repo that owns the Canvas):

```bash
python3 spec/meta/tools/ndf_replay.py guest-probe
```

Read `next_actions`. Do not skip ahead. Do not install Cube because probe
mentioned `vm`.

### 2. Apply `next_actions`

| Action | Do this |
| :--- | :--- |
| `enable_kvm` | Confirm `/dev/kvm` exists. Load `kvm_intel` or `kvm_amd`. Grant the current user `rw` (`kvm` group or ACL). Nested virt: `Y` is OK. No `/dev/kvm` → stop, `environment_blocked` is correct |
| `install_qemu` | Debian/Ubuntu: `sudo apt-get install -y qemu-system-x86 qemu-utils e2fsprogs`. Other distros: [packages.md](packages.md) |
| `install_docker` | Docker is only for **building** the guest image (`guest-image` uses a privileged container). Replay itself is qemu, not Docker |
| `guest_image` | `python3 spec/meta/tools/ndf_replay.py guest-image` (needs network + Docker). Writes `tmp/ndf-replay-images/alpine-ndf-replay/` (`vmlinuz`, `initramfs`, `rootfs.ext4`) |
| `chmod_image` | Image files MUST be readable by the qemu user: `chmod 644 vmlinuz initramfs rootfs.ext4` |
| `smoke_guest_run` | Step 4 |

Refuse:

- host-mount of live `repo_root` into the guest
- falling back to Composer / `isolate` / live `reconstruct` / `fake-vm` and calling it 已回放
- installing a Cube cluster unless the user explicitly asked for `--adapter cube`

### 3. Re-probe

`ready=true` requires: usable `/dev/kvm`, `qemu-system-x86_64`, readable kernel +
rootfs + initramfs.

### 4. Smoke guest-run

Pick any local Episode HEAD (`.ndf/replay/refs/episodes/<id>/HEAD`). If none
exist, install is done at `ready=true`; do not invent an Episode.

```bash
python3 spec/meta/tools/ndf_replay.py guest-run \
  --commit episodes/<id>/HEAD \
  --episode <id> \
  --adapter vm \
  --level R0
```

Pass only when `schema=ndf-replay-guest-proof/v1`, `valid=true`,
`isolation.adapter=vm`, `same_checkout=false`, `host_mount_used=false`,
`host_tracked_unchanged=true`, `host_head_unchanged=true`.

`environment_blocked` is a legal install result (missing KVM/image). Tell the
user the blocker. MUST NOT soft-fallback.

### 5. Report

Tell the human:

- `guest-probe.ready`
- smoke proof path / `valid`
- Canvas button is `guest-run --adapter vm` (no extra install on each click)

## Canvas / other agents

Replay buttons MUST keep using `--adapter vm` after install. If probe is not
ready, show `environment_blocked`; do not change the button to live reconstruct.

Point users here from `.cursor/skills/ndf-workflow-canvas/`.

## Optional Cube

Only if the user already has a Cube/E2B API: `--adapter cube` with
`NDF_CUBE_API_URL` + `NDF_CUBE_TEMPLATE_ID`. Proof still uses `adapter=vm` +
`hypervisor_backend=cube`. Still forbid host-mount. No API → blocked, not
“install Cube by default”.
