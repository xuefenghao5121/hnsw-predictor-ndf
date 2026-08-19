# NDF commander

React+D3 projection host for DiskHNSW NDF. Not SoT. Every visible control is an
id in [`action-registry.json`](action-registry.json). Enablement comes from
snapshot `enabledActions` (see [[META-011]]).

```bash
cd spec/meta/cockpit && npm install && npm run build
python3 spec/meta/tools/ndf_workflow_status.py snapshot --serve --topic hotspot-optimization
```

Open `http://127.0.0.1:8765/` on the machine that ran `--serve` (loopback only).
A Cloud Agent VM has no TCP ingress, so that URL is not reachable from the
human browser. On a Cloud Agent run:

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --out tmp/ndf-canvas-snapshot.json --topic hotspot-optimization --json
cd spec/meta/cockpit && npm run build && python3 build_standalone.py
```

Open `docs/ndf-commander.html` through the branch HTTPS preview. Canvas is not
part of the visualization or command chain.
Composer hops return a prompt; snapshot hops rebuild
`tmp/ndf-canvas-snapshot.json`. Button click is never `已确认` /
`TOPIC已审核` / `可以开始实现`.
