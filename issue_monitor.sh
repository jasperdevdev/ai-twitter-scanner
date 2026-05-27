#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Monitors the official Claude Code repo for issues
# Processes ALL new issues since last check (not just the latest one)
# Note: Uses read-only access (pull permission) since comments require push/triage access

REPO="anthropics/claude-code"
MCP_REPO="modelcontextprotocol/claude-server"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"
TRACKED_FILE="/root/.openclaw/workspace/ai-twitter-scanner/tracked_issues.jsonl"

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
    
    # Categorize the issue based on content patterns
    CATEGORY="unknown"
    LOWER_TITLE=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]')
    LOWER_BODY=$(echo "$ISSUE_BODY" | tr '[:upper:]' '[:lower:]')
    
    # Bug patterns: [BUG], bug:, not working, fails, doesn't, error, crash, broken, conflict
    if echo "$LOWER_TITLE" | grep -qiE '(\[bug\]|bug:|bug report|not working|fails|crash|error|doesn.?t|broken|conflict|incorrect|wrong)'; then
        CATEGORY="bug"
    # Feature patterns: [FEATURE], feature request, support, would be nice, capability, request
    elif echo "$LOWER_TITLE" | grep -qiE '(\[feature\]|feature request|add.*support|should.*support|would be nice|capability|request)'; then
        CATEGORY="feature"
    elif echo "$LOWER_TITLE" | grep -qiE '(\[docs?\]|documentation|document|missing doc)'; then
        CATEGORY="docs"
    elif echo "$LOWER_TITLE" | grep -qiE '(\[regression\]|regression|used to work|worked in)'; then
        CATEGORY="regression"
    elif echo "$LOWER_TITLE $LOWER_BODY" | grep -qiE '(memory|forget|ignore|amnesia)'; then
        CATEGORY="memory-issue"
    elif echo "$LOWER_TITLE $LOWER_BODY" | grep -qiE '(false.*positive|误报|safety|aup|policy.*violation)'; then
        CATEGORY="false-positive"
    fi
    
    # Record issue to tracked file (JSONL format for easy parsing)
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%MZ)
    echo "{\"number\":$ISSUE_NUM,\"title\":$(echo "$ISSUE_TITLE" | jq -Rs .),\"category\":\"$CATEGORY\",\"tracked_at\":\"$TIMESTAMP\"}" >> "$TRACKED_FILE"
    
    log "Tracked issue #$ISSUE_NUM [$CATEGORY]: $ISSUE_TITLE"
    
    # Update last processed issue (track the highest)
    if [ "$ISSUE_NUM" -gt "$LAST_PROCESSED" ]; then
        LAST_PROCESSED=$ISSUE_NUM
    fi
done

# Save the highest issue number processed
echo "$LAST_PROCESSED" > "$ISSUE_FILE"

log "Completed processing up to issue #$LAST_PROCESSED"