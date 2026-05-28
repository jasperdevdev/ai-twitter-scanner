# Claude Code Issues Analysis
# Generated: 2026-05-28 21:52 HKT

## Latest Issues (18 new)

### 🔴 Critical Bugs

**#63133: JSON parse error after tool execution**
- Bug: "Expecting value: line 1 column 1 (char 0)" after MCP tool execution
- Impact: Response corruption, session disruption
- Details: Happens with Playwright MCP tools on Windows, tool succeeds but parsing fails
- Regression: 2.1.153
- Labels: bug, platform:windows, area:mcp
- Note: Appears to be Python JSON parser error in client

**#63132: Agent fails to execute or respond to user input**
- Bug: Agent becomes unresponsive 
- Impact: Complete session failure

**#63128: Thinking display + interrupt button failure**
- Bug: With long context, thinking displays infinitely, interrupt button fails
- Platform: Windows

**#63120: MCP server tools silently discarded**
- Bug: 2.1.153 silently drops tools/list response from rmcp 0.12.0 HTTP MCP server
- Works in 2.1.152 but not 2.1.153 with identical wire protocol
- Impact: MCP tools unavailable despite successful handshake
- Regression from 2.1.152
- Suspects: inputSchema.$schema, annotations.openWorldHint, or missing capabilities.tools.listChanged

**#63127: Session name reverting after manual change**
- Bug: Manually renamed sessions revert
- Impact: User loses session naming work

**#63126: Native update fails behind proxy**
- Bug: 'socket connection was closed unexpectedly' — undici TLS incompatibility
- Platform: Behind corporate proxy

### 🟡 Medium Priority

**#63124: Cowork crashes on new chat**
- Platform: Windows (Italian error)
- Error: "Claude Code è andato in crash"

**#63123: Conversation continuation failure**
- Bug: Cannot continue conversations

**#63125: Unannounced quota changes**
- Impact: Users surprised by quota limits

**#63131: PTY handle leak**
- Bug: Leaks pseudo-terminals, exhausts on macOS after long sessions
- Platform: macOS

**#63138: VSCode terminal garbled text**
- VSCode terminal displays corrupted text with garbled symbols

### 🟢 Feature Requests / Unknown

**#63134**: Proactive unit test coverage recommendations
**#63129**: Honor tools: frontmatter for @mention agent invocation
**#63130**: macOS TCC popup recurring 
**#63135**: VS Code panel status line + terminal image paste in Codespaces
**#63136**: /powerup should show full catalog
**#63137**: Context contamination after auto-compact
**#63139**: LaTeX/KaTeX math rendering to TUI
**#63140**: Sub-agent PR review results not validated

---
Token lacks write permission to comment on issues directly.
Summary pushed to repo for tracking.
