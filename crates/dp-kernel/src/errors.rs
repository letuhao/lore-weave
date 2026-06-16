//! Typed errors for `dp-kernel`. Single enum so callers `match` once.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum EventError {
    /// L2.I: payload deserialization or required-field check failed.
    #[error("schema violation: type={event_type} version={event_version}: {detail}")]
    SchemaViolation {
        event_type: String,
        event_version: u32,
        detail: String,
    },

    /// L2.I: no schema registered for (event_type, event_version).
    #[error("unknown event schema: type={event_type} version={event_version}")]
    UnknownSchema {
        event_type: String,
        event_version: u32,
    },

    /// L2.H: requested upcast hop has no registered upcaster.
    #[error("missing upcaster: type={event_type} {from} -> {to}")]
    MissingUpcaster {
        event_type: String,
        from: u32,
        to: u32,
    },

    /// L2.H: caller asked for a downcast (`v3 -> v2`); forbidden — upcasters
    /// are forward-only because losing information when downcasting
    /// breaks replay determinism.
    #[error("backward upcast forbidden: type={event_type} from={from} to={to} (must be from < to)")]
    BackwardUpcast {
        event_type: String,
        from: u32,
        to: u32,
    },

    /// L2.H: the upcaster function itself returned an error (e.g. malformed
    /// source payload).
    #[error("upcaster failure: type={event_type} {from}->{to}: {detail}")]
    UpcasterFailed {
        event_type: String,
        from: u32,
        to: u32,
        detail: String,
    },
}
