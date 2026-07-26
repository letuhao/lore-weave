//! Service error enum → `service_http::ProblemDetails` (RFC 7807).
//!
//! Handlers return `Result<T, Error>`; axum renders the `IntoResponse` via the
//! `From<Error> for ProblemDetails` mapping. Tenancy denials map to 404 (a row
//! the caller may not see is indistinguishable from one that does not exist).

use axum::response::{IntoResponse, Response};
use service_http::ProblemDetails;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("not found")]
    NotFound,
    #[error("{0}")]
    BadRequest(String),
    #[error("{0}")]
    Conflict(String),
    /// An upstream dependency (chat-service) call failed.
    #[error("upstream call failed: {0}")]
    Upstream(String),
    #[error(transparent)]
    Db(#[from] sqlx::Error),
    #[error("{0}")]
    Internal(String),
}

impl From<Error> for ProblemDetails {
    fn from(err: Error) -> Self {
        match err {
            Error::NotFound => ProblemDetails::not_found("not found"),
            Error::BadRequest(m) => ProblemDetails::bad_request(m),
            Error::Conflict(m) => ProblemDetails::conflict(m),
            Error::Upstream(m) => ProblemDetails::bad_gateway(m),
            // A unique-violation surfaced from a write maps to 409; everything
            // else is an internal fault (don't leak SQL detail to the client).
            Error::Db(sqlx::Error::Database(dbe)) if dbe.is_unique_violation() => {
                ProblemDetails::conflict("a script with this code already exists")
            }
            Error::Db(sqlx::Error::Database(dbe)) if dbe.is_foreign_key_violation() => {
                ProblemDetails::conflict("script is in use by one or more sessions")
            }
            Error::Db(e) => {
                tracing::error!(%e, "database error");
                ProblemDetails::internal("database error")
            }
            Error::Internal(m) => {
                tracing::error!(detail = %m, "internal error");
                ProblemDetails::internal(m)
            }
        }
    }
}

impl IntoResponse for Error {
    fn into_response(self) -> Response {
        ProblemDetails::from(self).into_response()
    }
}

pub type Result<T> = std::result::Result<T, Error>;
