#!/usr/bin/env bash
# PreToolUse: inject a one-line reminder when Claude is about to Edit / Write
# a path that fires a trigger in AGENTS.md's index. Deduped per session so a
# long sweep costs one reminder per rule, not one per edit.
#
# Payload arrives on stdin as JSON (Claude Code PreToolUse contract).
# Response on stdout as JSON with a hookSpecificOutput.additionalContext.

set -euo pipefail

payload=$(cat)
path=$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<<"$payload")
if [ -z "$path" ]; then exit 0; fi

# Path patterns → reminder messages. Add arms here when a new path-shaped
# row lands in AGENTS.md's trigger index. Interview flags gate each arm;
# a project without a flag skips the arm entirely.
declare -A rule_for=()
case "$path" in
esac
if [ ${#rule_for[@]} -eq 0 ]; then exit 0; fi

# Session-keyed dedupe. If a marker for this rule already exists in the
# session's sentinel dir, skip; otherwise emit and touch the marker.
session=$(jq -r '.session_id // "nosession"' <<<"$payload")
sentinel="${TMPDIR:-/tmp}/claude-hooks/${session}"
mkdir -p "$sentinel"

reminders=()
for rule in "${!rule_for[@]}"; do
  marker="${sentinel}/${rule}"
  if [ ! -f "$marker" ]; then
    reminders+=("- ${rule_for[$rule]}")
    touch "$marker"
  fi
done

if [ ${#reminders[@]} -eq 0 ]; then exit 0; fi

context="Trigger index — rules that apply to $path (first reminder this session):"
for line in "${reminders[@]}"; do context+=$'\n'"$line"; done

jq -n --arg m "$context" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $m}}'
