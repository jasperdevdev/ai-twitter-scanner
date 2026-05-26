#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Monitors the official Claude Code repo for issues
# Processes ALL new issues since last check (not just the latest one)
# Note: Only adds comments if token has write access to the repo

REPO="anthropics/claude-code"
MCP_REPO="modelcontextprotocol/claude-server"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"

log() {
    echo "$(date): $1" >> "$LOG_FILE"
}

log "Checking for new issues..."

# Get all open issues sorted by creation date (newest first)
LATEST_ISSUES=$(gh api "repos/$REPO/issues?state=open&sort=created&direction=desc" --jq '.[].number' 2>/dev/null)

if [ -z "$LATEST_ISSUES" ]; then
    log "No open issues found"
    exit 0
fi

# Get last processed issue number
LAST_PROCESSED=0
if [ -f "$ISSUE_FILE" ]; then
    LAST_PROCESSED=$(cat "$ISSUE_FILE")
fi

# Find all issues newer than last processed
NEW_ISSUES=""
for issue_num in $LATEST_ISSUES; do
    if [ "$issue_num" -gt "$LAST_PROCESSED" ]; then
        NEW_ISSUES="$issue_num $NEW_ISSUES"
    fi
done

if [ -z "$NEW_ISSUES" ]; then
    log "No new issues (last processed: $LAST_PROCESSED)"
    exit 0
fi

log "Found new issues: $NEW_ISSUES"

# Spam detection: check if title contains excessive special Unicode chars (confusable spam)
is_spam() {
    local title="$1"
    local confusable_count=$(echo "$title" | grep -o '[⋆☆🎀✚卍🍉🍓❀💗【】＋➃𝕙ㄖ尺𝔸Ŝ卍♪♫♬]' | wc -l)
    local total_chars=$(echo "$title" | wc -c)
    # If >20% confusable chars, likely spam
    if [ "$confusable_count" -gt 0 ] && [ "$((confusable_count * 100 / total_chars))" -gt 20 ]; then
        return 0  # is spam
    fi
    # Check for known spam patterns
    if echo "$title" | grep -qiE '(infolinia|flynas|qatar|airways|polska|24h|call|center|customer service| номер|контактный|телефон)'; then
        local lower_title=$(echo "$title" | tr '[:upper:]' '[:lower:]')
        if [[ "$lower_title" == *"infolinia"* ]] || [[ "$lower_title" == *"polska"* ]]; then
            return 0  # is spam
        fi
    fi
    return 1  # not spam
}

# Process each new issue
for ISSUE_NUM in $NEW_ISSUES; do
    ISSUE_TITLE=$(gh api repos/$REPO/issues/$ISSUE_NUM --jq '.title')
    ISSUE_BODY=$(gh api repos/$REPO/issues/$ISSUE_NUM --jq '.body')
    
    # Skip spam issues
    if is_spam "$ISSUE_TITLE"; then
        log "Skipped issue #$ISSUE_NUM - detected as spam"
        LAST_PROCESSED=$ISSUE_NUM
        continue
    fi
    
    log "Processing issue #$ISSUE_NUM: $ISSUE_TITLE"
    
    # Try to add a comment
    COMMENT_RESULT=$(gh api repos/$REPO/issues/$ISSUE_NUM/comments -f body="👀 Issue received! I'll analyze this and work on a fix." 2>&1)
    COMMENT_EXIT=$?

    if [ $COMMENT_EXIT -eq 0 ]; then
        log "Acknowledged issue #$ISSUE_NUM"
    else
        if echo "$COMMENT_RESULT" | grep -qi "permission\|unauthorized\|403"; then
            log "Skipped comment - token lacks write permission for $REPO"
        else
            log "Comment failed: $COMMENT_RESULT"
        fi
    fi
    
    # Update last processed issue (track the highest)
    if [ "$ISSUE_NUM" -gt "$LAST_PROCESSED" ]; then
        LAST_PROCESSED=$ISSUE_NUM
    fi
done

# Save the highest issue number processed
echo "$LAST_PROCESSED" > "$ISSUE_FILE"

log "Completed processing up to issue #$LAST_PROCESSED"