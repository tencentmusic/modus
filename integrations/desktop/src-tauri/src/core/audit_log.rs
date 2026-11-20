//! Append-only audit log of user/system actions.
//!
//! Stored in the existing SQLite database (table `audit_log`). Writes are
//! best-effort: failures are swallowed so they never block the user action
//! they accompany. Reads return newest-first.
//!
//! The log is auto-pruned to `MAX_ENTRIES` rows on each write so the table
//! cannot grow unbounded.

use serde::Serialize;

/// Hard cap on log size. Older rows are dropped on insert.
pub const MAX_ENTRIES: i64 = 10_000;

/// One audit log entry as exposed to the frontend / exports.
#[derive(Debug, Clone, Serialize)]
pub struct AuditEntry {
    pub id: i64,
    /// Unix timestamp in seconds.
    pub ts: i64,
    /// Short action verb, e.g. "install", "remove", "enable", "sync".
    pub action: String,
    pub skill_id: Option<String>,
    pub skill_name: Option<String>,
    /// Affected tool/agent key when the action targets one, e.g. "claude_code".
    pub tool: Option<String>,
    pub success: bool,
    /// Free-form detail. Error message on failure, optional context otherwise.
    pub detail: Option<String>,
}

/// Payload used when recording a new entry.
#[derive(Debug, Default, Clone)]
pub struct AuditDraft {
    pub action: String,
    pub skill_id: Option<String>,
    pub skill_name: Option<String>,
    pub tool: Option<String>,
    pub success: bool,
    pub detail: Option<String>,
}

impl AuditDraft {
    pub fn new(action: impl Into<String>) -> Self {
        Self {
            action: action.into(),
            ..Default::default()
        }
    }

    pub fn ok(mut self) -> Self {
        self.success = true;
        self
    }

    pub fn fail(mut self, error: impl Into<String>) -> Self {
        self.success = false;
        self.detail = Some(error.into());
        self
    }

    pub fn skill(mut self, id: impl Into<String>, name: impl Into<String>) -> Self {
        self.skill_id = Some(id.into());
        self.skill_name = Some(name.into());
        self
    }

    pub fn tool(mut self, tool: impl Into<String>) -> Self {
        self.tool = Some(tool.into());
        self
    }

    pub fn detail(mut self, detail: impl Into<String>) -> Self {
        self.detail = Some(detail.into());
        self
    }
}
