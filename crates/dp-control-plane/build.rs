//! Generates the tonic server and client from `contracts/proto/`.
//!
//! The proto lives in `contracts/` rather than in this crate because it is a
//! CONTRACT, not an implementation detail: `contracts/` is where this repo puts
//! artifacts that more than one component must agree on, and a second consumer
//! (a Go admin CLI, a TypeScript operator tool) must read the same bytes rather
//! than a copy that drifted.
//!
//! `cargo:rerun-if-changed` on the proto is load-bearing. Without it cargo
//! fingerprints only this crate's Rust sources, so editing the contract would
//! leave the generated code stale — the build would stay green while the server
//! served the previous version of the surface, which is precisely the drift the
//! contract exists to prevent.

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto = "../../contracts/proto/dp_control_plane.proto";
    println!("cargo:rerun-if-changed={proto}");
    // …and on the directory, so a NEW proto added beside it is picked up. A
    // rerun key that names only today's files is default-uncovered for
    // tomorrow's.
    println!("cargo:rerun-if-changed=../../contracts/proto");

    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(&[proto], &["../../contracts/proto"])?;
    Ok(())
}
