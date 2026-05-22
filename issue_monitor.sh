#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Monitors the official Claude Code repo for issues
# Note: Only adds comments if token has write access to the repo

REPO="anthropics/claude-code"
# Also monitor MCP issues separately if needed
MCP_REPO="modelcontextprotocol/claude-server"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"

echo "$(date): Checking for new issues..." >> "$LOG_FILE"

# Get latest issue number (including closed issues)
LATEST_ISSUE=$(gh api "repos/$REPO/issues?state=all" --jq 'sort_by(.created_at) | reverse | .[0].number' 2>/dev/null)

if [ -z "$LATEST_ISSUE" ] || [ "$LATEST_ISSUE" == "null" ]; then
    echo "$(date): No issues found" >> "$LOG_FILE"
    exit 0
fi

# Check if we already processed this issue
if [ -f "$ISSUE_FILE" ]; then
    LAST_PROCESSED=$(cat "$ISSUE_FILE")
    if [ "$LATEST_ISSUE" == "$LAST_PROCESSED" ]; then
        echo "$(date): No new issues (latest: $LATEST_ISSUE)" >> "$LOG_FILE"
        exit 0
    fi
fi

# New issue found!
echo "$(date): New issue found: #$LATEST_ISSUE" >> "$LOG_FILE"

# Get issue details
ISSUE_TITLE=$(gh api repos/$REPO/issues/$LATEST_ISSUE --jq '.title')
ISSUE_BODY=$(gh api repos/$REPO/issues/$LATEST_ISSUE --jq '.body')

echo "Issue #$LATEST_ISSUE: $ISSUE_TITLE" >> "$LOG_FILE"
echo "Body: $ISSUE_BODY" >> "$LOG_FILE"

# Save last processed issue
echo "$LATEST_ISSUE" > "$ISSUE_FILE"

# Try to add a comment (only works if token has write access)
COMMENT_RESULT=$(gh api repos/$REPO/issues/$LATEST_ISSUE/comments -f body="👀 Issue received! I'll analyze this and work on a fix." 2>&1)
COMMENT_EXIT=$?

if [ $COMMENT_EXIT -eq 0 ]; then
    echo "$(date): Acknowledged issue #$LATEST_ISSUE" >> "$LOG_FILE"
else
    # Check if it's a permission error
    if echo "$COMMENT_RESULT" | grep -qi "permission\|unauthorized\|403"; then
        echo "$(date): Skipped comment - token lacks write permission for $REPO" >> "$LOG_FILE"
    else
        echo "$(date): Comment failed: $COMMENT_RESULT" >> "$LOG_FILE"
    fi
fi

# Log full issue details for analysis
echo "$(date): Issue received, will analyze..." >> "$LOG_FILE"