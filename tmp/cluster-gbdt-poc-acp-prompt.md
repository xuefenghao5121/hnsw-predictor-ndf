【track=poc】topic: cluster-gbdt
repo_root: /home/huawei/hnsw-predictor-ndf
Approved content SHA: ff9dcadcd53cf705ed5ba87d6fd66e0438177db989c5b062f9d3e8c1c05ae905
Context plan SHA: 77a405eadb3db8137189d032638389f4e12abacc759179116c758b6ee75ffdf7
Manifest SHA: ff94e66296baa169bd7304db0181540ecad7b1d4e93e5110efcf69d17a9639a4
Episode ID: ep-poc-implementation-cluster-gbdt-20260814T090921Z

ACP handshake (MUST use these exact values; do not create another worktree/session):
{
  "run_id": "run-poc-implementation-cluster-gbdt-20260814T090921Z",
  "session_id": "d21779ab-aad3-408c-a717-f871eae0884e",
  "repo_root": "/home/huawei/hnsw-predictor-ndf",
  "base_sha": "a14339234133cc6c5a2348464954f744c6465efb",
  "worktree": "/home/huawei/hnsw-predictor-ndf/.worktrees/cluster-gbdt-poc-20260814T090921Z",
  "branch": "poc/cluster-gbdt-implementation-20260814T090921Z",
  "allowed_write_root": "poc/cluster-gbdt/",
  "status": "running"
}

CWD is already the isolated worktree. All writes MUST stay under poc/cluster-gbdt/ in this worktree.
Forbidden: src/, include/, tests/, stable SLA, spec/meta/, production patches in spec/models/.
Forbidden sections: topic_contract, design_contract, perf_bind, delta_hypothesis, interface_contract, gate_receipts.
Allowed sections: poc_code, perf_numbers, delta_rounds, evidence, commits_append, topic_runtime_headers.

BEFORE ANY WORK:
1. Run `python3 spec/meta/tools/ndf_context.py context-verify --manifest /home/huawei/hnsw-predictor-ndf/tmp/cluster-gbdt-poc-manifest.json --plan /home/huawei/hnsw-predictor-ndf/tmp/cluster-gbdt-poc-plan.json --strict --json`
2. Require valid=true and plan_sha exactly 77a405eadb3db8137189d032638389f4e12abacc759179116c758b6ee75ffdf7. If drifted, STOP and do not write.

Read only this order (then graph closure already compiled into the plan):
TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → GATES → COMMITS.
Do not steal observation numbers from SLA/NOTES prose.

Task:
R0 remeasure is already verified (baseline_status=current). Continue exploring A1 from DELTA Rounds/candidates: cluster entropy / per-cluster signal vs old purity, on current Trunk a143392, without amending DESIGN/TOPIC contract or DELTA hypothesis.

1. Prefer existing `poc/cluster-gbdt/r1_entropy_analysis.py` (groundtruth-based). Use `cluster_assignments_1M.npy` if present else `cluster_assignments_100k.npy`, and `data/sift_groundtruth_official.ivecs`.
2. Do NOT start the heavy PQ coarse simulation unless entropy analysis finishes and clearly warrants a cheap extra check you can complete in this run.
3. Write evidence under `poc/cluster-gbdt/ndf/evidence/` (log + markdown summary with commands, SHAs, numbers).
4. Append a DELTA Rounds row only (not hypothesis). Append COMMITS.md ledger row. Update NOTES.md if needed.
5. If you change files, git add only under poc/cluster-gbdt/ and commit with trailers:
   Topic: cluster-gbdt
   Proposals: N/A
   Clauses: BEH-025, BEH-034, BEH-037
   Then append ndf/COMMITS.md if not already updated in that commit.

Return at the end a single JSON object (also write it to poc/cluster-gbdt/ndf/evidence/poc-implementation-completion.json) with:
{
  "schema": "ndf-agent-completion/v1",
  "run_id": "run-poc-implementation-cluster-gbdt-20260814T090921Z",
  "session_id": "d21779ab-aad3-408c-a717-f871eae0884e",
  "status": "completed|failed",
  "topic": "cluster-gbdt",
  "task": "poc_implementation",
  "track": "poc",
  "base_sha": "a14339234133cc6c5a2348464954f744c6465efb",
  "repo_head": "<git sha after work>",
  "worktree": "/home/huawei/hnsw-predictor-ndf/.worktrees/cluster-gbdt-poc-20260814T090921Z",
  "branch": "poc/cluster-gbdt-implementation-20260814T090921Z",
  "manifest_sha": "ff94e66296baa169bd7304db0181540ecad7b1d4e93e5110efcf69d17a9639a4",
  "context_plan_sha": "77a405eadb3db8137189d032638389f4e12abacc759179116c758b6ee75ffdf7",
  "changed_files": [],
  "changed_file_shas": {},
  "changed_sections": [],
  "git_commit": "<sha or empty>",
  "reproduce": [],
  "evidence_paths": [],
  "evidence_bundle_sha": "<sha256 of concatenated evidence files or empty>",
  "summary": "<text>",
  "result": "success|failed",
  "blockers": [],
  "coverage": "completion_only"
}

Also run post-checks from the worktree and include receipts:
- python3 spec/meta/tools/ndf_poc_isolation.py check --topic cluster-gbdt --workspace --report -
- python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic cluster-gbdt --json
Save outputs under ndf/evidence/post-check-*.txt/json.

Do not synthesize ACP stream events. coverage=completion_only is required.
Do not write outside poc/cluster-gbdt/.
Do not mark TOPIC promoted or close the topic.
