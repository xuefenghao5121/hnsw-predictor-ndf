# NDF commander

React+D3 projection host for DiskHNSW NDF. Not SoT. Every visible control is an
id in [`action-registry.json`](action-registry.json). Enablement comes from
snapshot `enabledActions` (see [[META-011]]).

```bash
cd spec/meta/cockpit && npm install && npm run build
python3 spec/meta/tools/ndf_workflow_status.py snapshot --serve --json
```

Open `http://127.0.0.1:8765/` on the machine that ran `--serve` (loopback only).
`--topic` is optional (Topics workbench focus only). After a local Agent writes
`tmp/ndf-canvas-snapshot.json`, this live page auto-reloads. htmlpreview is a
static backup and does not auto-refresh.

A Cloud Agent VM has no TCP ingress, so that URL is not reachable from the
human browser. On a Cloud Agent run:

```bash
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --out tmp/ndf-canvas-snapshot.json --topic hotspot-optimization --json
cd spec/meta/cockpit && npm run build && python3 build_standalone.py
```

`docs/ndf-commander.html` is self-contained: snapshot, React bundle, D3 and CSS
are all inline. It has no GitHub/CDN/runtime network dependency. Delivery options:

```bash
# Directly open on a desktop
xdg-open docs/ndf-commander.html

# Or serve on localhost / an intranet host
python3 -m http.server 8766 --directory docs
# open http://127.0.0.1:8766/ndf-commander.html
```

The current public preview uses GitHub Raw + HTMLPreview only as one hosting
choice. Users without GitHub access can copy the single HTML file, serve it
with nginx/Apache/object storage, or open it from disk. Rebuilding requires the
repository plus Python/Node dependencies, but using an already-built HTML file
does not. Canvas is not part of the visualization or command chain.
Composer hops return a prompt; snapshot hops rebuild
`tmp/ndf-canvas-snapshot.json`. Button click is never `已确认` /
`TOPIC已审核` / `可以开始实现`.
