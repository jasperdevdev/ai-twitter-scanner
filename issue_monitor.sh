#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Runs every 30 minutes to check for new issues

REPO="jasperdevdev/ai-twitter-scanner"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"

echo "$(date): Checking for new issues..." >> "$LOG_FILE"

# Get latest issue number created by user
LATEST_ISSUE=$(gh api repos/$REPO/issues --jq 'sort_by(.created_at) | reverse | .[0].number' 2>/dev/null)

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

# TODO: Implement issue fixing logic here
# For now, just acknowledge the issue
echo "$(date): Issue received, will process..." >> "$LOG_FILE"

# Save last processed issue
echo "$LATEST_ISSUE" > "$ISSUE_FILE"

# Add a comment to the issue
gh api repos/$REPO/issues/$LATEST_ISSUE/comments -f body="👀 Issue received! I'll work on this and submit a fix."

echo "$(date): Acknowledged issue #$LATEST_ISSUE" >> "$LOG_FILE"