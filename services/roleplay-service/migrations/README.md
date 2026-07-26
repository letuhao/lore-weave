# Migrations

sqlx::migrate!("./migrations") runs these at startup (service_http::db::init).
R0: none yet (infra gate). R1 adds 0001_init.sql (roleplay_scripts + rp_sessions + rp_memory + System seed).
