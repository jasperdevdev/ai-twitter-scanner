#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Monitors the official Claude Code repo for issues
# Processes ALL new issues since last check (not just the latest one)
# Note: Uses read-only access (pull permission) since comments require push/triage access

# Configuration
REPO="anthropics/claude-code"
MCP_REPO="modelcontextprotocol/claude-server"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"
TRACKED_FILE="/root/.openclaw/workspace/ai-twitter-scanner/tracked_issues.jsonl"
DUPE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/duplicates.txt"
ANALYSIS_FILE="/root/.openclaw/workspace/ai-twitter-scanner/latest_issues_analysis.md"

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

# Spam detection: check if title contains excessive special Unicode chars
is_spam() {
    local title="$1"
    local confusable_count=$(echo "$title" | grep -o '[⋆☆🎀✚卍🍉🍓❀💗【】＋➃𝕙ㄖ尺𝔸Ŝ卍♪♫♬]' | wc -l)
    local total_chars=$(echo "$title" | wc -c)
    if [ "$confusable_count" -gt 0 ] && [ $((confusable_count * 100 / total_chars)) -gt 20 ]; then
        return 0
    fi
    if echo "$title" | grep -qiE '(infolinia|flynas|qatar|airways|polska|24h|call|center|customer service| номер|контактный|телефон)'; then
        local lower_title=$(echo "$title" | tr '[:upper:]' '[:lower:]')
        if [[ "$lower_title" == *"infolinia"* ]] || [[ "$lower_title" == *"polska"* ]]; then
            return 0
        fi
    fi
    return 1
}

# Normalize issue title for duplicate detection
normalize_title() {
    local title="$1"
    title=$(echo "$title" | tr '[:upper:]' '[:lower:]')
    title=$(echo "$title" | sed -E 's/\[[0-9]+\] //g')
    title=$(echo "$title" | sed -E 's/^\[bug\]//g')
    title=$(echo "$title" | sed -E 's/^\[feature\]//g')
    title=$(echo "$title" | sed -E 's/^\[docs?\]//g')
    title=$(echo "$title" | sed -E 's/^\[regression\]//g')
    title=$(echo "$title" | sed -E 's/^\[bug\]//g')
    title=$(echo "$title" | sed -E 's/v[0-9]+\.[0-9]+\.[0-9]+//g')
    title=$(echo "$title" | sed -E 's/[0-9]{4,}.*//g')
    echo "$title" | xargs
}

# Check for duplicates in last N tracked issues
is_duplicate() {
    local title="$1"
    local normalized=$(normalize_title "$title")

    if [ -f "$TRACKED_FILE" ]; then
        local recent_titles=$(tail -20 "$TRACKED_FILE" | jq -r '.title' 2>/dev/null)
        for old_title in $recent_titles; do
            local old_normalized=$(normalize_title "$old_title")
            if [ -n "$old_normalized" ] && [ -n "$normalized" ]; then
                local match=$(echo "$normalized" | grep -o "$old_normalized" | wc -l)
                if [ "$match" -gt 0 ]; then
                    return 0
                fi
                local match2=$(echo "$old_normalized" | grep -o "$normalized" | wc -l)
                if [ "$match2" -gt 0 ]; then
                    return 0
                fi
            fi
        done
    fi
    return 1
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

    # Check for duplicates
    if is_duplicate "$ISSUE_TITLE"; then
        log "Skipped issue #$ISSUE_NUM - detected as duplicate of existing issue"
        echo "$ISSUE_NUM" >> "$DUPE_FILE"
        LAST_PROCESSED=$ISSUE_NUM
        continue
    fi

    log "Processing issue #$ISSUE_NUM: $ISSUE_TITLE"

    # Categorize the issue based on content patterns
    CATEGORY="unknown"
    LOWER_TITLE=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]')
    LOWER_BODY=$(echo "$ISSUE_BODY" | tr '[:upper:]' '[:lower:]')

    # Bug patterns
    if echo "$LOWER_TITLE" | grep -qiE '(\[bug\]|bug:|bug report|not working|fails|crash|error|doesn.?t|broken|conflict|incorrect|wrong)'; then
        CATEGORY="bug"
    # Feature patterns
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

    # Record issue to tracked file
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%MZ)
    echo "{\"number\":$ISSUE_NUM,\"title\":$(echo "$ISSUE_TITLE" | jq -Rs .),\"category\":\"$CATEGORY\",\"tracked_at\":\"$TIMESTAMP\"}" >> "$TRACKED_FILE"

    log "Tracked issue #$ISSUE_NUM [$CATEGORY]: $ISSUE_TITLE"

    # Update last processed issue
    if [ "$ISSUE_NUM" -gt "$LAST_PROCESSED" ]; then
        LAST_PROCESSED=$ISSUE_NUM
    fi
done

# Save the highest issue number processed
echo "$LAST_PROCESSED" > "$ISSUE_FILE"

log "Completed processing up to issue #$LAST_PROCESSED"