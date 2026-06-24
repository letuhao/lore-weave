//! `sim` — the S10 simulation runner. One subcommand per oracle so the
//! conformance runner (Inc-6) can shell `sim <case> [--bite]`. Exit codes:
//!   0 = pass · 1 = fail (a counterexample / soundness violation) · 2 = notrun.

use std::process::{Command, ExitCode};

use loreweave_sim::{atomicity, cas, convergence, skeleton, tilemap};

fn report(case: &str, r: Result<String, String>) -> ExitCode {
    match r {
        Ok(summary) => {
            println!("[sim] PASS {case} — {summary}");
            ExitCode::SUCCESS
        }
        Err(why) => {
            eprintln!("[sim] FAIL {case} — {why}");
            ExitCode::from(1)
        }
    }
}

/// The cross-process determinism leg: spawn THIS binary as `sim tilemap --child
/// <seed>` and confirm the child's digest matches the in-process one. Proves
/// `place_tilemap` is byte-stable across a process boundary.
fn tilemap_cross_process() -> Result<String, String> {
    let exe = std::env::current_exe().map_err(|e| format!("current_exe: {e}"))?;
    for seed in tilemap::CROSS_PROCESS_SEEDS {
        let out = Command::new(&exe)
            .args(["tilemap", "--child", &seed.to_string()])
            .output()
            .map_err(|e| format!("spawn child: {e}"))?;
        if !out.status.success() {
            return Err(format!("child exited non-zero for seed {seed}"));
        }
        let child = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let local = tilemap::digest(seed, false);
        if child != local {
            return Err(format!(
                "cross-process DRIFT at seed {seed}: child {child} != local {local}"
            ));
        }
    }
    Ok(format!(
        "cross-process byte-stable over {} seeds",
        tilemap::CROSS_PROCESS_SEEDS.len()
    ))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    let case = args.get(1).map(String::as_str).unwrap_or("");
    let bite =
        args.iter().any(|a| a == "--bite") || std::env::var("SIM_BITE").as_deref() == Ok("1");

    match case {
        "skeleton" => report("skeleton", skeleton::self_check()),
        "convergence" => report("convergence", convergence::check(bite)),
        "atomicity" => report("atomicity", atomicity::check(bite)),
        "cas" => report("cas", cas::check(bite)),
        "tilemap" => {
            // Child mode: print one digest and exit (the cross-process leg).
            if let Some(pos) = args.iter().position(|a| a == "--child") {
                let seed: u64 = args.get(pos + 1).and_then(|s| s.parse().ok()).unwrap_or(0);
                println!("{}", tilemap::digest(seed, false));
                return ExitCode::SUCCESS;
            }
            let inproc = tilemap::check_inprocess(bite);
            // For a bite or a failure, report directly; a clean run also does
            // the cross-process leg.
            if bite || inproc.is_err() {
                return report("tilemap", inproc);
            }
            let combined =
                inproc.and_then(|a| tilemap_cross_process().map(|b| format!("{a}; {b}")));
            report("tilemap", combined)
        }
        "" => {
            eprintln!("[sim] usage: sim <skeleton|convergence|atomicity|cas|tilemap> [--bite]");
            ExitCode::from(2)
        }
        other => {
            eprintln!("[sim] unknown case '{other}' (not yet implemented)");
            ExitCode::from(2)
        }
    }
}
