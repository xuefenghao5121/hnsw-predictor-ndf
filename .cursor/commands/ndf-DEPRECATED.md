---
description: Deprecated — use ndf-workflow skill (ADR-META-004)
---

# Deprecated slash command

Commander button atoms are retired. Use the unique skill:

`.cursor/skills/ndf-workflow/SKILL.md`

Human phrases: **初始化项目** / **提交 Idea** / **派发** / **继续** / **关闭**.

CLI examples:

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack --task product_proposal --intent-file tmp/intent.md --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack --task ndf_improvement_proposal --origin human_intent --intent-file tmp/intent.md --json
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch --topic <topic> --intent implement --send --json
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote
```
