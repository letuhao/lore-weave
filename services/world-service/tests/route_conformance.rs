//! Route conformance — the router, the route table, and the OpenAPI contract
//! must agree, in every direction.
//!
//! Contract-first is a repo rule, and for glossary-service it is enforced by
//! `TestOpenAPIRouteConformance`, which `chi.Walk`s the real router against the
//! frozen YAML. This is that pattern for a Rust service, and it exists because
//! **`contracts/.spectral.yaml` is NOT WIRED** (DEFERRED 078): freezing a YAML
//! here buys no machine check at all by itself. Without this test, "the contract
//! is frozen" would be a claim wearing the costume of evidence.
//!
//! ## Three checks, because two of them can be satisfied vacuously
//!
//! 1. **Every documented operation is routed.** Catches a phantom path.
//! 2. **Every route in the table is documented.** Catches an undocumented route.
//! 3. **The table lists every `.route("…")` literal in the source.** Checks 1
//!    and 2 compare a hand-maintained list against a hand-maintained document —
//!    a route added straight to `build_router` appears in neither, so both pass
//!    and the route is invisible. This check is what makes the table a
//!    *witness* rather than a *restatement*: it walks the tree.
//!
//! Each carries a **reach** assertion. A walk that reaches nothing and a clean
//! tree are byte-identical, including the exit code.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use world_service::server::{Gate, ROUTES};

/// Directory holding this service's frozen contracts.
const SPEC_DIR: &str = "contracts/api/world";

/// The service's own source tree, walked for route literals.
const SRC_DIR: &str = "services/world-service/src";

/// The shared health module contributes `/livez` `/readyz` `/metrics` by merge,
/// so its literals live outside this service and still have to be accounted for.
const SHARED_HEALTH: &str = "crates/service-http/src/health.rs";

/// The embedding **worker's** probe router — a different binary on a different
/// port, so its routes are deliberately not in this service's table.
///
/// A reasoned exclusion, and a CHECKED one: the test asserts the file still
/// exists and still belongs to the worker. A silent exclusion of a file that
/// was renamed or repurposed is how an exemption channel starts.
const WORKER_ROUTER: &str = "services/world-service/src/embedding_queue/live/server.rs";

/// HTTP methods an OpenAPI path item may declare. Anything else under a path
/// (`parameters`, `summary`, `servers`) is not an operation.
const METHODS: [&str; 7] = ["get", "put", "post", "delete", "options", "head", "patch"];

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR is services/world-service.
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// Every `(method, path)` operation declared by every contract in `SPEC_DIR`.
fn documented() -> BTreeSet<(String, String)> {
    let dir = repo_root().join(SPEC_DIR);
    let mut out = BTreeSet::new();
    let mut files = 0usize;

    let entries = std::fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("REACH: cannot read the contract directory {dir:?}: {e}"));
    for entry in entries {
        let path = entry.expect("dir entry").path();
        if path.extension().and_then(|s| s.to_str()) != Some("yaml") {
            continue;
        }
        files += 1;
        let text = std::fs::read_to_string(&path).expect("read spec");
        let doc: serde_yaml::Value = serde_yaml::from_str(&text)
            .unwrap_or_else(|e| panic!("{path:?} is not parseable YAML: {e}"));
        let paths = doc
            .get("paths")
            .and_then(|p| p.as_mapping())
            .unwrap_or_else(|| panic!("{path:?} declares no `paths:` mapping"));
        for (route, item) in paths {
            let route = route.as_str().expect("path key is a string");
            let item = item.as_mapping().unwrap_or_else(|| panic!("{route} is not a mapping"));
            for (method, _) in item {
                let method = method.as_str().unwrap_or_default().to_ascii_lowercase();
                if METHODS.contains(&method.as_str()) {
                    out.insert((method, route.to_string()));
                }
            }
        }
    }

    // REACH — the directory exists but holds no contract, or every contract
    // parsed to zero operations. Both produce an empty set that would satisfy
    // "every documented operation is routed" perfectly.
    assert!(files > 0, "REACH: no *.yaml under {dir:?} — the contract home is empty");
    assert!(
        out.len() >= 3,
        "REACH: parsed {files} contract file(s) but found only {} operation(s); \
         the paths walk is not reaching the document",
        out.len()
    );
    out
}

/// Every `(method, path)` in the service's route table.
fn tabled() -> BTreeSet<(String, String)> {
    ROUTES.iter().map(|r| (r.method.to_string(), r.path.to_string())).collect()
}

#[test]
fn every_documented_operation_is_routed() {
    let missing: Vec<_> = documented().difference(&tabled()).cloned().collect();
    assert!(
        missing.is_empty(),
        "the contract documents {} operation(s) this service does not serve: {missing:?}\n\
         Either add them to `server::routes::ROUTES` (and to `build_router`), or remove them \
         from {SPEC_DIR}. A documented-but-unrouted path is a promise to a caller that 404s.",
        missing.len()
    );
}

#[test]
fn every_routed_operation_is_documented() {
    let undocumented: Vec<_> = tabled().difference(&documented()).cloned().collect();
    assert!(
        undocumented.is_empty(),
        "this service serves {} operation(s) no contract in {SPEC_DIR} documents: {undocumented:?}\n\
         Contract-first: freeze it in the YAML in the same commit.",
        undocumented.len()
    );
}

/// Collect every route literal MOUNTED in a source file.
///
/// Comment lines are dropped first. On its first run this walk flagged a route
/// named inside **this test's own doc comment** — prose that happens to live in
/// a source file, which is exactly what defeated the deferral registry's
/// coverage check until its stripper was fixed. It failed loud rather than
/// silent, which is the safe direction, but a gate whose documentation trips it
/// is a gate authors learn to work around.
///
/// Only whole comment LINES are dropped, never a trailing `//` on a code line:
/// cutting mid-line would truncate a DSN like `postgres://…` and could hide a
/// real mount. The residue is that `foo(); // .route("/x")` still registers —
/// a false positive, which is loud, rather than a false negative, which is not.
fn route_literals(text: &str) -> Vec<String> {
    let code: String = text
        .lines()
        .filter(|l| !l.trim_start().starts_with("//"))
        .collect::<Vec<_>>()
        .join("\n");
    let mut out = Vec::new();
    let mut rest = code.as_str();
    while let Some(i) = rest.find(".route(\"") {
        rest = &rest[i + ".route(\"".len()..];
        if let Some(end) = rest.find('"') {
            out.push(rest[..end].to_string());
            rest = &rest[end..];
        }
    }
    out
}

#[test]
fn the_route_table_lists_every_route_literal_in_the_source() {
    let root = repo_root();
    let tabled_paths: BTreeSet<&str> = ROUTES.iter().map(|r| r.path).collect();

    // Walk the WHOLE source tree rather than an enumerated file list: a route
    // added in a file created tomorrow must be in scope the day it lands. An
    // enumerated list is default-uncovered, which is NV-3.
    let mut stack = vec![root.join(SRC_DIR)];
    let mut visited = 0usize;
    let mut found: Vec<(String, String)> = Vec::new();
    let worker = root.join(WORKER_ROUTER);

    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir).unwrap_or_else(|e| panic!("read {dir:?}: {e}")) {
            let path = entry.expect("dir entry").path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if path.extension().and_then(|s| s.to_str()) != Some("rs") {
                continue;
            }
            visited += 1;
            if path == worker {
                continue;
            }
            let text = std::fs::read_to_string(&path).expect("read source");
            for lit in route_literals(&text) {
                found.push((lit, path.display().to_string()));
            }
        }
    }

    // The shared health module contributes three routes by merge. If it grows a
    // fourth, this service's table must account for it — that is the point.
    let health = root.join(SHARED_HEALTH);
    let health_text = std::fs::read_to_string(&health)
        .unwrap_or_else(|e| panic!("REACH: cannot read {health:?}: {e}"));
    let health_lits = route_literals(&health_text);
    assert!(
        !health_lits.is_empty(),
        "REACH: found no `.route(` literal in {SHARED_HEALTH}; the probe merge is not being read"
    );
    for lit in health_lits {
        found.push((lit, SHARED_HEALTH.to_string()));
    }

    // REACH — an empty walk passes the membership check trivially.
    assert!(
        visited >= 15,
        "REACH: walked only {visited} .rs file(s) under {SRC_DIR}; the tree walk is not reaching \
         the source"
    );
    assert!(
        found.len() >= 4,
        "REACH: found only {} route literal(s) across the walk; expected at least the four this \
         service serves",
        found.len()
    );

    let stray: Vec<_> =
        found.iter().filter(|(lit, _)| !tabled_paths.contains(lit.as_str())).collect();
    assert!(
        stray.is_empty(),
        "{} route(s) are mounted in source but absent from `server::routes::ROUTES`: {stray:?}\n\
         The table is what the OpenAPI contract is checked against, so a route missing from it \
         is undocumented AND unnoticed. Add it to ROUTES and to {SPEC_DIR}.",
        stray.len()
    );
}

#[test]
fn the_worker_router_exclusion_still_names_the_worker() {
    // The exclusion above is reasoned; this is the check that keeps it honest.
    let path = repo_root().join(WORKER_ROUTER);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "REACH: {WORKER_ROUTER} is excluded from the route walk but cannot be read ({e}). \
             If it moved, move the exclusion; if it is gone, delete the exclusion."
        )
    });
    assert!(
        !route_literals(&text).is_empty(),
        "{WORKER_ROUTER} is excluded as the worker's router but mounts no routes; \
         the exclusion no longer describes the file and must be removed."
    );
    assert!(
        text.contains("worker") || text.contains("DEFERRED-059"),
        "{WORKER_ROUTER} no longer identifies itself as the embedding worker's surface; \
         re-justify or remove the exclusion rather than letting it cover a service route."
    );
}

#[test]
fn the_contract_and_the_table_agree_on_which_routes_are_gated() {
    // The gate column is not decoration: `WS-F4` says every versioned route is
    // internal. The contract says the same thing with `security:`. Check them
    // against each other so neither can drift alone.
    let text = std::fs::read_to_string(repo_root().join(SPEC_DIR).join("provisioning.v1.yaml"))
        .expect("read provisioning contract");
    let doc: serde_yaml::Value = serde_yaml::from_str(&text).expect("parse");
    let paths = doc.get("paths").and_then(|p| p.as_mapping()).expect("paths");

    let mut checked = 0usize;
    for spec in ROUTES {
        let item = paths
            .get(serde_yaml::Value::String(spec.path.to_string()))
            .unwrap_or_else(|| panic!("{} is not in the contract", spec.path));
        let op = item
            .get(serde_yaml::Value::String(spec.method.to_string()))
            .unwrap_or_else(|| panic!("{} {} is not in the contract", spec.method, spec.path));
        let secured = op.get("security").is_some();
        assert_eq!(
            secured,
            spec.gate == Gate::Internal,
            "{} {}: the table says {:?} but the contract {} a `security:` block",
            spec.method,
            spec.path,
            spec.gate,
            if secured { "declares" } else { "omits" }
        );
        checked += 1;
    }
    assert_eq!(checked, ROUTES.len(), "REACH: not every table row was compared");
    assert!(checked >= 4, "REACH: only {checked} route(s) compared");
}
