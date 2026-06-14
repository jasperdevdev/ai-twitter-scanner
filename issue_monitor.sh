#!/bin/bash
# GitHub Issue Monitor for ai-twitter-scanner
# Monitors the official Claude Code repo for issues

# Configuration
REPO="anthropics/claude-code"
ISSUE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/.last_issue"
LOG_FILE="/root/.openclaw/workspace/ai-twitter-scanner/issue_monitor.log"
TRACKED_FILE="/root/.openclaw/workspace/ai-twitter-scanner/tracked_issues.jsonl"
DUPE_FILE="/root/.openclaw/workspace/ai-twitter-scanner/duplicates.txt"

# Save progress on exit (including SIGTERM)
save_progress() {
    if [ -n "$LAST_PROCESSED" ] && [ "$LAST_PROCESSED" -gt 0 ]; then
        echo "$LAST_PROCESSED" > "$ISSUE_FILE"
        log "Progress saved: last processed = $LAST_PROCESSED"
    fi
}
trap save_progress EXIT

log() {
    echo "$(date): $1" >> "$LOG_FILE"
}

# Limit to most recent 20 issues for efficiency
MAX_ISSUES=20
log "Checking for new issues..."

# Get all open issues sorted by creation date (newest first)
LATEST_ISSUES=$(gh api "repos/$REPO/issues?state=open&sort=created&direction=desc&per_page=$MAX_ISSUES" --jq '.[].number' 2>/dev/null)

if [ -z "$LATEST_ISSUES" ]; then
    log "No open issues found"
    exit 0
fi

# Get last processed issue number
LAST_PROCESSED=0
if [ -f "$ISSUE_FILE" ]; then
    LAST_PROCESSED=$(cat "$ISSUE_FILE")
fi

# Find all issues newer than last processed (limit to 5 per run to prevent timeout)
NEW_ISSUES=""
COUNT=0
for issue_num in $LATEST_ISSUES; do
    if [ "$issue_num" -gt "$LAST_PROCESSED" ] && [ $COUNT -lt 5 ]; then
        NEW_ISSUES="$issue_num $NEW_ISSUES"
        COUNT=$((COUNT + 1))
    fi
done

if [ -z "$NEW_ISSUES" ]; then
    log "No new issues (last processed: $LAST_PROCESSED)"
    exit 0
fi

log "Found new issues: $NEW_ISSUES"

# Spam detection
is_spam() {
    local title="$1"
    local body="$2"
    
    # Check for empty or very short titles (likely invalid GitHub issues)
    local title_len=$(echo "$title" | wc -c)
    if [ "$title_len" -lt 5 ]; then
        return 0  # Treat empty/very-short titles as spam
    fi
    
    # Check for thank you notes / non-issue messages
    local lower_body
    lower_body=$(echo "$body" | tr '[:upper:]' '[:lower:]' 2>/dev/null | tr -d '\0' 2>/dev/null) || true
    if [ -n "$lower_body" ]; then
        if echo "$lower_body" | grep -qiE 'not a bug|not a feature|thank you|thanks|gratitude|appreciate|no technical|positive experience|great job|well done'; then
            return 0
        fi
    fi
    
    local confusable_count=0
    for spam_char in "⋆" "☆" "🎀" "✚" "卍" "🍉" "🍓" "❀" "💗" "【" "】" "＋"; do
        count=$(echo "$title" | grep -Fo "$spam_char" 2>/dev/null | wc -l) || true
        confusable_count=$((confusable_count + count))
    done
    local total_chars=$(echo "$title" | wc -c)
    if [ "$total_chars" -gt 0 ] && [ "$confusable_count" -gt 0 ] && [ $((confusable_count * 100 / total_chars)) -gt 20 ]; then
        return 0
    fi
    local lower_title
    lower_title=$(echo "$title" | tr '[:upper:]' '[:lower:]' 2>/dev/null | tr -d '\0' 2>/dev/null) || true
    if [ -n "$lower_title" ]; then
        case "$lower_title" in
            *infolinia*|*flynas*|*qatar*|*airways*|*polska*|*24h*|*call*|*center*|*customer*service*|*номер*|*контактный*|*телефон*)
                return 0
                ;;
        esac
    fi
    return 1
}

# Normalize issue title - removes tags, version numbers, etc
normalize_title() {
    local title="$1"
    title=$(echo "$title" | tr '[:upper:]' '[:lower:]' 2>/dev/null) || echo "$title"
    # Remove common tags at start of title (with optional whitespace)
    title=$(echo "$title" | sed -E 's/^\[bug\]\s*//g' 2>/dev/null) || true
    title=$(echo "$title" | sed -E 's/^\[feature\]\s*//g' 2>/dev/null) || true
    title=$(echo "$title" | sed -E 's/^\[docs?\]\s*//g' 2>/dev/null) || true
    title=$(echo "$title" | sed -E 's/^\[regression\]\s*//g' 2>/dev/null) || true
    title=$(echo "$title" | sed -E 's/^\[MODEL\]\s*//g' 2>/dev/null) || true
    # Remove version numbers (v1.2.3) but preserve other content
    title=$(echo "$title" | sed -E 's/v[0-9]+\.[0-9]+\.[0-9]+//g' 2>/dev/null) || true
    # Remove trailing issue numbers like #12345 but preserve the rest
    title=$(echo "$title" | sed -E 's/#[0-9]{4,}\. *//g' 2>/dev/null) || true
    # Trim whitespace
    echo "$title" | xargs 2>/dev/null || echo "$title"
}

# Check for duplicates - require substantially similar titles (not just keywords)
is_duplicate() {
    local title="$1"
    local normalized
    normalized=$(normalize_title "$title") || true
    
    if [ -z "$normalized" ]; then
        return 1
    fi
    
    # Get the issue number to avoid self-comparison
    local current_issue_num=$(echo "$title" | grep -oE '[0-9]+' | head -1) || true
    
    # Only flag as duplicate if the normalized title is substantial (at least 25 chars)
    # This prevents short generic phrases from matching too easily
    local normalized_len=$(echo "$normalized" | wc -c)
    if [ "$normalized_len" -lt 25 ]; then
        return 1
    fi
    
    if [ -f "$TRACKED_FILE" ]; then
        # Compare against full normalized titles line by line
        while IFS= read -r old_title; do
            [ -z "$old_title" ] && continue
            local old_normalized
            old_normalized=$(normalize_title "$old_title") || true
            # Only flag as duplicate if EXACT match AND substantial length
            if [ "$normalized" = "$old_normalized" ] && [ -n "$old_normalized" ]; then
                local old_len=$(echo "$old_normalized" | wc -c)
                if [ "$old_len" -ge 25 ]; then
                    return 0
                fi
            fi
        done < <(tail -30 "$TRACKED_FILE" | jq -r '.title' 2>/dev/null)
    fi
    return 1
}

# Batch fetch all new issues in one call (faster)
batch_fetch_issues() {
    local nums="$NEW_ISSUES"
    for ISSUE_NUM in $nums; do
        gh api "repos/$REPO/issues/$ISSUE_NUM" --jq '{title: .title, body: .body[0:500]}' 2>/dev/null
    done
}

# Track current batch titles for duplicate detection within batch
declare -A BATCH_TITLES

# Process each new issue
for ISSUE_NUM in $NEW_ISSUES; do
    # Single API call to get both title and body (truncated body for speed)
    ISSUE_DATA=$(gh api "repos/$REPO/issues/$ISSUE_NUM" --jq '{title: .title, body: .body[0:500]}' 2>/dev/null)
    ISSUE_TITLE=$(echo "$ISSUE_DATA" | jq -r '.title')
    ISSUE_BODY=$(echo "$ISSUE_DATA" | jq -r '.body')

    # Skip spam issues (including thank you notes and non-issues)
    if is_spam "$ISSUE_TITLE" "$ISSUE_BODY"; then
        log "Skipped issue #$ISSUE_NUM - detected as spam/non-issue"
        LAST_PROCESSED=$ISSUE_NUM
        echo "$LAST_PROCESSED" > "$ISSUE_FILE"
        continue
    fi

    # Check for duplicates against tracked issues AND current batch
    if is_duplicate "$ISSUE_TITLE"; then
        log "Skipped issue #$ISSUE_NUM - detected as duplicate of existing issue"
        echo "$ISSUE_NUM" >> "$DUPE_FILE"
        LAST_PROCESSED=$ISSUE_NUM
        echo "$LAST_PROCESSED" > "$ISSUE_FILE"
        continue
    fi
    
    # Also check against current batch titles (in-memory duplicate detection)
    normalized=$(normalize_title "$ISSUE_TITLE")
    for batch_title in "${!BATCH_TITLES[@]}"; do
        batch_normalized=$(normalize_title "$batch_title")
        if [ "$normalized" = "$batch_normalized" ]; then
            log "Skipped issue #$ISSUE_NUM - duplicate of issue in same batch"
            echo "$ISSUE_NUM" >> "$DUPE_FILE"
            LAST_PROCESSED=$ISSUE_NUM
            echo "$LAST_PROCESSED" > "$ISSUE_FILE"
            continue 2
        fi
    done
    # Add this title to batch tracking
    BATCH_TITLES["$ISSUE_TITLE"]="$ISSUE_NUM"

    log "Processing issue #$ISSUE_NUM: $ISSUE_TITLE"

    # Categorize the issue based on content patterns
    CATEGORY="unknown"
    LOWER_TITLE=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]')
    LOWER_BODY=$(echo "$ISSUE_BODY" | tr '[:upper:]' '[:lower:]')

    # Check for thank you notes / non-issues (defensive - should have been caught by spam filter)
    if echo "$LOWER_BODY" | grep -qiE 'not a bug|not a feature|thank you|thanks|gratitude|appreciate|no technical'; then
        CATEGORY="non-issue"
    elif echo "$LOWER_TITLE" | grep -qiE '(\[bug\]|bug:|bug report|not working|fails|crash|error|doesn.?t|broken|conflict|incorrect|wrong)'; then
        CATEGORY="bug"
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

    # Record issue to tracked file (ensure file exists first)
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%MZ)
    touch "$TRACKED_FILE" 2>/dev/null || true
    echo "{\"number\":$ISSUE_NUM,\"title\":$(echo "$ISSUE_TITLE" | jq -Rs .),\"category\":\"$CATEGORY\",\"tracked_at\":\"$TIMESTAMP\"}" >> "$TRACKED_FILE"

    log "Tracked issue #$ISSUE_NUM [$CATEGORY]: $ISSUE_TITLE"

    if [ "$ISSUE_NUM" -gt "$LAST_PROCESSED" ]; then
        LAST_PROCESSED=$ISSUE_NUM
    fi
done

echo "$LAST_PROCESSED" > "$ISSUE_FILE"

log "Completed processing up to issue #$LAST_PROCESSED"