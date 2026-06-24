//! Inc-5 tilemap determinism-DST as cargo tests, including the cross-process
//! leg (spawns the built `sim` binary via `CARGO_BIN_EXE_sim`).

use std::process::Command;

use loreweave_sim::tilemap;

#[test]
fn deterministic_in_process() {
    tilemap::check_inprocess(false).expect("place_tilemap must be byte-stable in-process");
}

#[test]
fn bite_nondeterminism_is_caught() {
    tilemap::check_inprocess(true).expect("injected nondeterminism must break the gate");
}

#[test]
fn deterministic_across_process() {
    let exe = env!("CARGO_BIN_EXE_sim");
    for seed in tilemap::CROSS_PROCESS_SEEDS {
        let out = Command::new(exe)
            .args(["tilemap", "--child", &seed.to_string()])
            .output()
            .expect("spawn sim child");
        assert!(out.status.success(), "child failed for seed {seed}");
        let child = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let local = tilemap::digest(seed, false);
        assert_eq!(child, local, "cross-process digest drift at seed {seed}");
    }
}
