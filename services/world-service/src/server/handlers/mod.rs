//! HTTP handlers, one module per resource.
//!
//! Split by resource rather than gathered into one file, and the reason is not
//! only tidiness: `reality-id-adoption-gate`'s exemptions are PREFIX matches, so
//! a single `handlers.rs` would carry the provisioning path's exemption over
//! every route added beside it. The geography routes this service exists for
//! (GEO_001) act on realities that are open and bindable — they SHOULD be held
//! to `dp::RealityId`. A new file is default-uncovered by the exemption table,
//! which means default-ADOPTABLE, which is the safe direction.

pub mod realities;
