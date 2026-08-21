#!/usr/bin/env bash
# RETIRED: pack auto-dispatch via afterShellExecution is disabled (hooks.json).
# Command Agent must run dispatch-send after human 「派发」. Kept for reference only.
# Formerly: when control-pack|repair-pack|pack succeeds with safe_to_dispatch,
# send OpenClaw / Claude Code ACP, wait for result, then
# completion-record → action-commit → snapshot.
set -u
printf '%s\n' '{}'
exit 0
