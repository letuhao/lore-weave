//! `DFO-7` — the `spine` BINARY, driven, and required to EXIT.
//!
//! # Why the binary and not its parts
//!
//! Every other live smoke in this crate drives components: an island, a writer,
//! an admission call. That is why `DFO-7` survived. `spine --drain-once` blocked
//! forever on the first statement of its first loop iteration — `BLOCK 0` is
//! Redis for *wait indefinitely*, and the binding-signal rail passed exactly
//! that under a comment promising the opposite — and **not one test noticed**,
//! because nothing in the suite ever started the process a deployment runs.
//!
//! A unit check now guards the root cause and runs everywhere with no stack
//! (`bus::read_options_tests`). This is the other half: proof that the assembled
//! binary terminates. The two fail for different reasons, which is the point —
//! the unit one reds if the argument comes back, this one reds if ANY future
//! edit reintroduces a block on the drain path, whatever its cause.
//!
//! # Running it
//!
//! ```text
//!   bash scripts/smoke/spine-drain-once.sh
//! ```
//!
//! which creates the two throwaway databases, applies the migrations and sets
//! the three variables below. Absent them the test SKIPS, loudly, naming the
//! script — a live smoke that silently passes with no stack is worse than one
//! that is not written.

use std::io::Read;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

const META_DSN_VAR: &str = "SPINE_SMOKE_META_TEST_DATABASE_URL";
const CHANNEL_DSN_VAR: &str = "SPINE_SMOKE_CHANNEL_TEST_DATABASE_URL";
const REDIS_VAR: &str = "SPINE_SMOKE_REDIS_URL";

/// How long a `--drain-once` run may take before we call it hung.
///
/// Generous on purpose: the failure this catches is UNBOUNDED (the measured
/// symptom ran past 120s), so a slow box cannot produce a false red — only a
/// genuine block can.
const PATIENCE: Duration = Duration::from_secs(90);

/// Refuse a DSN whose database name does not announce itself as disposable.
///
/// The same guard `epoch_live_common` applies, and for the same reason: this
/// test seeds rows, and an unscoped fixture pointed at a real database has
/// already destroyed user data in this project once.
fn guarded(var: &str) -> Option<String> {
    let raw = std::env::var(var).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"].iter().any(|m| db.contains(m)),
        "{var} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

fn env3() -> Option<(String, String, String)> {
    Some((guarded(META_DSN_VAR)?, guarded(CHANNEL_DSN_VAR)?, std::env::var(REDIS_VAR).ok()?))
}

/// Register a FRESH reality in the meta DB and give it one channel.
///
/// Fresh per run rather than reused: `--create-reality` binds a ruleset ONCE
/// (`RLS-A3`), so a reality carried over from a previous run refuses the second
/// invocation — a failure about creation semantics, in a test about liveness.
async fn seed(meta_dsn: &str, channel_dsn: &str, reality: Uuid, channel: i64) {
    let meta = PgPoolOptions::new().max_connections(2).connect(meta_dsn).await.expect("meta DSN");
    sqlx::query(
        "INSERT INTO reality_registry \
           (reality_id, db_host, db_name, status, locale, \
            session_max_pcs, session_max_npcs, session_max_total, deploy_cohort) \
         VALUES ($1, 'pg-shard-0.internal', 'spine_drain_once_smoke', 'active', 'en', 4, 16, 20, 0)",
    )
    .bind(reality)
    .execute(&meta)
    .await
    .expect("seed reality_registry — is the meta DB migrated? see scripts/smoke/spine-drain-once.sh");

    let chan = PgPoolOptions::new().max_connections(2).connect(channel_dsn).await.expect("channel DSN");
    sqlx::query(
        "INSERT INTO channels (reality_id, id, parent, level_name, display_name, depth, lifecycle) \
         VALUES ($1, $2, NULL, 'root', 'drain-once smoke', 0, 'active')",
    )
    .bind(reality)
    .bind(channel)
    .execute(&chan)
    .await
    .expect("seed channels — is the channel DB migrated? see scripts/smoke/spine-drain-once.sh");
}

/// Drain a child pipe on its own thread.
///
/// **Not a convenience.** Reading the pipes only after the process exits means a
/// binary that outprints the pipe buffer blocks on the write, never exits, and
/// is reported by this test as `DFO-7` — a red for a cause that is not the one
/// named. `BDR-50`: a wrong-reason red is the failure mode that most resembles
/// success, and a hang detector that can itself cause the hang is the worst
/// place to have one.
fn drain(pipe: impl Read + Send + 'static) -> std::thread::JoinHandle<String> {
    std::thread::spawn(move || {
        let mut s = String::new();
        let mut p = pipe;
        let _ = p.read_to_string(&mut s);
        s
    })
}

/// Wait for `child`, killing it at [`PATIENCE`]. `None` = it had to be killed.
fn wait_bounded(child: &mut std::process::Child) -> Option<std::process::ExitStatus> {
    let deadline = Instant::now() + PATIENCE;
    loop {
        match child.try_wait().expect("try_wait") {
            Some(st) => return Some(st),
            None if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
            None => std::thread::sleep(Duration::from_millis(200)),
        }
    }
}

/// `DFO-7`. With entries waiting on the stream, `--drain-once` must consume
/// them, report, and TERMINATE.
///
/// Asserting the exit status alone would be satisfied by a binary that died on
/// a connection error, so the report line is asserted too: it is printed after
/// the loop breaks and therefore cannot appear on any path that did not run.
#[tokio::test(flavor = "multi_thread")]
async fn the_spine_binary_drains_once_and_exits() {
    let Some((meta_dsn, channel_dsn, redis_url)) = env3() else {
        eprintln!(
            "SKIP the_spine_binary_drains_once_and_exits — set {META_DSN_VAR}, \
             {CHANNEL_DSN_VAR} and {REDIS_VAR}, or run scripts/smoke/spine-drain-once.sh"
        );
        return;
    };

    let reality = Uuid::new_v4();
    let channel = 1i64;
    seed(&meta_dsn, &channel_dsn, reality, channel).await;

    // Two entries, both destined for a rejection: this test is about the loop
    // TERMINATING, and a rejection is a full pass through it (admit → commit
    // through the SDK → ack). The resolution path has its own live coverage.
    let client = redis::Client::open(redis_url.clone()).expect("redis url");
    let mut conn = redis::aio::ConnectionManager::new(client).await.expect("redis");
    let stream = format!("reality:{reality}:cell:{channel}:proposals");
    // The consumer group is created at `$`, so the entries must be added AFTER
    // the binary creates it or they are never delivered — except that the group
    // does not exist yet for a brand-new reality, and `XGROUP CREATE MKSTREAM`
    // on an existing stream starts from its end. Creating the group here, at
    // `0`, is what makes the pre-existing entries visible to the run below.
    //
    // The result is CHECKED, not discarded: the reality is new on every run, so
    // `BUSYGROUP` cannot occur and any error here is a real one. Swallowed, it
    // would reach the assertions as `consumed: 0` and read like a drain bug.
    redis::cmd("XGROUP")
        .arg("CREATE").arg(&stream).arg(format!("reality:{reality}")).arg("0").arg("MKSTREAM")
        .query_async::<()>(&mut conn).await
        .expect("create the consumer group at 0 so the pre-added entries are delivered");
    for body in [r#"{"not":"a proposal"}"#, r#"{"still":"not one"}"#] {
        let _: String = redis::cmd("XADD")
            .arg(&stream).arg("*").arg("proposal").arg(body)
            .query_async(&mut conn).await.expect("XADD");
    }

    let mut child = Command::new(env!("CARGO_BIN_EXE_spine"))
        .args(["--redis-url", &redis_url])
        .args(["--pg-url", &channel_dsn])
        .args(["--meta-url", &meta_dsn])
        .args(["--meta-allowlist", "../../contracts/meta/events_allowlist.yaml"])
        .args(["--reality", &reality.to_string()])
        .args(["--channel", &channel.to_string()])
        .args(["--ruleset-state", "../../.loreweave/rulesets"])
        .arg("--create-reality")
        .arg("--drain-once")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn the spine binary");

    let out_h = drain(child.stdout.take().expect("stdout piped"));
    let err_h = drain(child.stderr.take().expect("stderr piped"));

    let waited = wait_bounded(&mut child);
    let stdout = out_h.join().expect("stdout reader");
    let stderr = err_h.join().expect("stderr reader");

    let Some(status) = waited else {
        panic!(
            "`spine --drain-once` did not exit within {}s — this is DFO-7. The last thing it \
             printed before the original hang was the epoch-signal line, because \
             `drain_and_reconcile` is the FIRST statement of the loop and its fetch blocked \
             forever on an almost-always-empty stream.",
            PATIENCE.as_secs()
        );
    };

    assert!(
        status.success(),
        "spine exited {status}\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
    );
    assert!(
        stdout.contains("== spine report =="),
        "spine exited 0 but never reached its report — it did not run the loop.\n{stdout}"
    );
    assert!(
        stdout.contains("consumed  : 2"),
        "the drain must have consumed BOTH waiting entries.\n{stdout}"
    );
}
