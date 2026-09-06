#[derive(Debug)]
pub enum DpError {
    RateLimited,
    CircuitOpen,
}

fn write() -> Result<u32, DpError> {
    Ok(1)
}

// Each of the three discarding methods R-6 names.
pub fn swallow_with_ok() {
    let _ = write().ok();
}

pub fn swallow_with_unwrap_or_default() -> u32 {
    write().unwrap_or_default()
}

pub fn swallow_with_unwrap_or_else() -> u32 {
    write().unwrap_or_else(|_| 0)
}

// Must NOT fire: a Result whose error is not a DpError.
pub fn unrelated_ok_is_fine() {
    let r: Result<u32, std::num::ParseIntError> = "x".parse();
    let _ = r.ok();
}

// Must NOT fire: propagating is the whole point.
pub fn propagating_is_fine() -> Result<u32, DpError> {
    let v = write()?;
    Ok(v)
}
