// Reaches no kernel client. The lint MUST NOT fire.
use std::collections::HashMap;

pub fn m() -> HashMap<u8, u8> { HashMap::new() }
