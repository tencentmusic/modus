use anyhow::{Context, Result};
use fs2::FileExt;
use std::fs::{File, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::time::{Duration, Instant};

use super::central_repo;

/// Filename used for the central-repository write lock.
///
/// The lock lives in `base_dir()` (the parent of `skills_dir()`), not inside
/// `skills_dir` itself. `skills_dir` gets renamed/recreated during clone and
/// reclone flows, and on Windows mandatory file locking makes it impossible
/// to rename a directory that contains a file held with an exclusive lock —
/// see issue #99 (os error 5 / "Access is denied").
const LOCK_FILE_NAME: &str = ".skills-manager.lock";

/// How long a user-initiated ("foreground") operation waits for the central
/// repository lock before giving up with a "busy" error. Background work holds
/// the lock only briefly per skill, but an auto-backup `git push` can hold it
/// for ~10–15s, so we wait comfortably longer than the longest expected
/// background hold. Without this wait, a foreground install/update/tag/delete
/// that happened to collide with a background update check or backup failed
/// instantly with "skills repository is busy" (issues #196, #220, #232).
pub const FOREGROUND_WAIT: Duration = Duration::from_secs(20);

/// Poll cadence while waiting for the lock. Kept below the yield the background
/// per-skill loops insert between releases (see `skill_auto_updater` and the
/// tray check) so a waiting foreground op reliably wins the lock during that
/// window instead of being starved by the background re-acquiring immediately.
const POLL_INTERVAL: Duration = Duration::from_millis(50);

pub struct RepoLock {
    file: File,
}

impl RepoLock {
    /// Acquire the lock, failing immediately if it is already held. Used by
    /// background loops that prefer to skip a unit of work and retry on the
    /// next round rather than block a user-initiated operation.
    pub fn acquire(operation: &str) -> Result<Self> {
        let file = open_lock_file()?;
        file.try_lock_exclusive()
            .with_context(|| format!("skills repository is busy: {operation}"))?;
        Self::stamp(file, operation)
    }

    /// Acquire the lock, waiting up to `timeout` for a concurrent holder to
    /// release it before reporting the repository as busy. Used by
    /// user-initiated operations so transient contention with background work
    /// (update checks, auto-backup) surfaces as a short wait, not an error.
    pub fn acquire_blocking(operation: &str, timeout: Duration) -> Result<Self> {
        let file = open_lock_file()?;
        let start = Instant::now();
        loop {
            match file.try_lock_exclusive() {
                Ok(()) => return Self::stamp(file, operation),
                // Retry on any error (not just `WouldBlock`): on Windows
                // `LockFileEx` reports contention as `ERROR_LOCK_VIOLATION`,
                // which does not map to `ErrorKind::WouldBlock`, so gating on
                // the kind would defeat the wait on the very platform that
                // needs it most.
                Err(err) => {
                    if start.elapsed() >= timeout {
                        return Err(err).with_context(|| {
                            format!("skills repository is busy: {operation}")
                        });
                    }
                    std::thread::sleep(POLL_INTERVAL);
                }
            }
        }
    }

    /// Convenience for user-initiated operations: wait up to [`FOREGROUND_WAIT`].
    pub fn acquire_foreground(operation: &str) -> Result<Self> {
        Self::acquire_blocking(operation, FOREGROUND_WAIT)
    }

    /// Records who holds the lock, so a "repository is busy" report can be
    /// traced back to the operation sitting on it.
    ///
    /// Deliberately not fsynced. Mutual exclusion comes from `flock`, never from
    /// this file's contents, so a stamp lost to a crash costs nothing — whereas
    /// `File::sync_all` is `fcntl(F_FULLFSYNC)` on macOS, which flushes the
    /// whole APFS volume's cache and bills every page of it, including other
    /// processes' dirty pages, to whoever called it. Phase B of
    /// `check_all_skill_updates` takes this lock once per skill (deliberately —
    /// see the comment there), so on a library of ~75 skills that was 75
    /// whole-volume barriers per round: one hour of it was reported by the
    /// system as 2.1 GB of "file backed memory dirtied", 24x over the
    /// disk-writes limit, with the truncate and write above stalled behind the
    /// same barriers.
    fn stamp(mut file: File, operation: &str) -> Result<Self> {
        file.set_len(0)?;
        file.seek(SeekFrom::Start(0))?;
        writeln!(
            file,
            "pid={}\nhostname={}\noperation={}\nstart_time={}",
            std::process::id(),
            std::env::var("HOSTNAME")
                .or_else(|_| std::env::var("COMPUTERNAME"))
                .unwrap_or_else(|_| "unknown".to_string()),
            operation,
            chrono::Utc::now().to_rfc3339()
        )?;
        Ok(Self { file })
    }
}

fn open_lock_file() -> Result<File> {
    let base = central_repo::base_dir();
    std::fs::create_dir_all(&base)?;
    let lock_path = base.join(LOCK_FILE_NAME);
    OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .open(&lock_path)
        .with_context(|| format!("failed to open repo lock {}", lock_path.display()))
}

impl Drop for RepoLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    /// Regression test for issue #99: the lock file must not live inside
    /// `skills_dir`. On Windows, an open exclusive lock on a file inside a
    /// directory makes it impossible to rename or remove that directory
    /// (Access is denied / os error 5), which broke the clone-with-backup
    /// flow used by "use existing remote backup".
    #[test]
    fn lock_file_lives_outside_skills_dir() {
        let _guard = central_repo::test_base_dir_lock();
        let tmp = tempdir().unwrap();
        let base = tmp.path().join("base");
        central_repo::set_test_base_dir_override(Some(base.clone()));
        let skills_dir = central_repo::skills_dir();
        std::fs::create_dir_all(&skills_dir).unwrap();

        let lock = RepoLock::acquire("test").unwrap();

        assert!(base.join(LOCK_FILE_NAME).exists());
        assert!(!skills_dir.join(LOCK_FILE_NAME).exists());

        let entries: Vec<_> = std::fs::read_dir(&skills_dir).unwrap().collect();
        assert!(
            entries.is_empty(),
            "skills_dir should remain empty while the lock is held; got {entries:?}"
        );

        drop(lock);
        central_repo::set_test_base_dir_override(None);
    }

    /// The stamp is the only reason the lock file has contents at all, and it
    /// is written without an fsync — so pin down that a separate reader still
    /// sees it. `File` does no userspace buffering, so the `write` reaches the
    /// page cache before `stamp` returns; losing it to a crash would be
    /// harmless, but losing it to buffering would silently blank the one clue
    /// a "repository is busy" report has.
    ///
    /// Unix only, and not for lack of trying: fs2 locks the whole byte range
    /// with `LockFileEx`, whose locks are mandatory on Windows, so *no* handle
    /// can read the file while the lock is held — the assertion below cannot be
    /// expressed there. Asserting it after the release instead would pass
    /// whether or not the write ever reached the file, which is no assertion at
    /// all. The same mandatory lock means a Windows operator cannot read the
    /// stamp of a live holder either, so there is less to protect.
    #[cfg(unix)]
    #[test]
    fn stamp_is_readable_by_another_handle_while_held() {
        let _guard = central_repo::test_base_dir_lock();
        let tmp = tempdir().unwrap();
        let base = tmp.path().join("base");
        central_repo::set_test_base_dir_override(Some(base.clone()));

        let lock = RepoLock::acquire("diagnosable operation").unwrap();

        let stamped = std::fs::read_to_string(base.join(LOCK_FILE_NAME)).unwrap();
        assert!(
            stamped.contains(&format!("pid={}", std::process::id())),
            "stamp should name the holding process; got {stamped:?}"
        );
        assert!(
            stamped.contains("operation=diagnosable operation"),
            "stamp should name the operation; got {stamped:?}"
        );

        drop(lock);
        central_repo::set_test_base_dir_override(None);
    }

    /// A blocking acquire must report "busy" only after waiting roughly the
    /// requested timeout while another holder keeps the lock, and must succeed
    /// once that holder releases. This is the behaviour foreground operations
    /// rely on to ride out transient contention with background work.
    #[test]
    fn blocking_acquire_waits_then_times_out_and_recovers() {
        let _guard = central_repo::test_base_dir_lock();
        let tmp = tempdir().unwrap();
        let base = tmp.path().join("base");
        central_repo::set_test_base_dir_override(Some(base));

        let held = RepoLock::acquire("holder").unwrap();

        let start = Instant::now();
        let busy = RepoLock::acquire_blocking("waiter", Duration::from_millis(300));
        assert!(busy.is_err(), "should time out while the lock is held");
        assert!(
            start.elapsed() >= Duration::from_millis(250),
            "should have waited close to the timeout, waited {:?}",
            start.elapsed()
        );

        drop(held);
        let recovered = RepoLock::acquire_blocking("waiter", Duration::from_millis(300));
        assert!(recovered.is_ok(), "should acquire once the holder releases");
        drop(recovered);

        central_repo::set_test_base_dir_override(None);
    }
}
