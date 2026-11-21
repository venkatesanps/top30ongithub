---
id: commit-message-from-file
trigger: "when a commit message has several lines"
confidence: 0.55
domain: "git"
source: "session-observation"
scope: project
last_seen: 2026-11-18
---

# Commit message from a file

## Action
Write the message to a temp file and use `git commit -F`, not a heredoc in `-m`.

## Evidence
- 2026-11-12 fix: heredoc in -m failed in bash 3.2; -F worked (8ae1ec78:1236)
- 2026-11-18 correction: user said use a file for long commit messages
