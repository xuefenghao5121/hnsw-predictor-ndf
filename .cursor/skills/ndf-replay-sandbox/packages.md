# Guest VM host packages

Default path is Linux + KVM. Other OS: stop and report `environment_blocked`.

## Debian / Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y qemu-system-x86 qemu-utils e2fsprogs
```

Docker (image build only), if `guest-probe` says `install_docker`:

```bash
sudo apt-get install -y docker.io
sudo usermod -aG docker "$USER"
```

KVM access (if `/dev/kvm` exists but is not writable):

```bash
sudo usermod -aG kvm "$USER"
# or: sudo setfacl -m u:$USER:rw /dev/kvm
```

Group changes need a new login. ACL is enough for the current session.

## Fedora / RHEL

```bash
sudo dnf install -y qemu-system-x86 qemu-img e2fsprogs
```

## Arch

```bash
sudo pacman -S --needed qemu-system-x86 qemu-img e2fsprogs
```

## After packages

```bash
python3 spec/meta/tools/ndf_replay.py guest-image
python3 spec/meta/tools/ndf_replay.py guest-probe
```

`guest-image` pulls `alpine:3.21` and needs Docker `--privileged` once to pack
the ext4 rootfs. Replay later does not use Docker.
