//! The host's wall clock, rendered as RFC-3339.
//!
//! **The kernel never sees this.** Commit timestamps are the host's job — a
//! deterministic island cannot read a clock without becoming unreplayable — so
//! the split is architectural, not stylistic, and the function lives outside
//! `sim-core` for that reason rather than for tidiness.
//!
//! Lifted out of `bin/spine.rs` in `Q0b B3c`, when the epoch-activated append
//! became a second caller. It had been a private helper in the binary; a second
//! copy in the committer is exactly how two producers end up stamping the same
//! channel with two different renderings of the same instant.

/// `YYYY-MM-DDTHH:MM:SSZ` — seconds precision, UTC.
///
/// Hand-rolled rather than `chrono` because this crate's dependency list is
/// load-bearing (the laws must stay reachable from a no-I/O tier) and the whole
/// requirement is one format with no parsing, no zones and no locale.
pub fn now_rfc3339() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock after epoch")
        .as_secs();
    from_unix_secs(secs)
}

/// The pure half, so the formatting is testable without a clock.
pub fn from_unix_secs(secs: u64) -> String {
    let days = secs / 86_400;
    let (mut y, mut rem_days) = (1970i64, days as i64);
    loop {
        let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
        let len = if leap { 366 } else { 365 };
        if rem_days < len {
            break;
        }
        rem_days -= len;
        y += 1;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let months = [31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0;
    while rem_days >= months[m] {
        rem_days -= months[m];
        m += 1;
    }
    let (h, mi, s) = ((secs / 3600) % 24, (secs / 60) % 60, secs % 60);
    format!("{y:04}-{:02}-{:02}T{h:02}:{mi:02}:{s:02}Z", m + 1, rem_days + 1)
}

#[cfg(test)]
mod tests {
    use super::from_unix_secs;

    #[test]
    fn the_epoch_itself() {
        assert_eq!(from_unix_secs(0), "1970-01-01T00:00:00Z");
    }

    /// A leap day, which is the only part of this arithmetic that is easy to get
    /// wrong and impossible to notice for four years.
    #[test]
    fn a_leap_day() {
        // 2024-02-29T12:34:56Z
        assert_eq!(from_unix_secs(1_709_210_096), "2024-02-29T12:34:56Z");
    }

    /// 2100 is NOT a leap year (divisible by 100, not by 400) — the clause a
    /// naive `% 4` gets wrong.
    #[test]
    fn the_century_that_is_not_a_leap_year() {
        // 2100-03-01T00:00:00Z
        assert_eq!(from_unix_secs(4_107_542_400), "2100-03-01T00:00:00Z");
    }
}
