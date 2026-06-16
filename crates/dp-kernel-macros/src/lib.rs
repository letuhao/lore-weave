//! `dp-kernel-macros` — proc-macros for [`dp-kernel`](https://docs.rs/dp-kernel).
//!
//! ## Scope (RAID cycle 17 / L4.B)
//!
//! Two surfaces:
//!
//! 1. `#[derive(Aggregate)]` — emits impls of
//!    [`dp_kernel::Aggregate`] + [`dp_kernel::AggregateMeta`] for a struct
//!    that uses `#[handles_event("name")]` attributes on methods to declare
//!    its event-handling map.
//!
//! 2. `#[handles_event("type")]` — informational helper attribute attached
//!    to methods inside an `impl` block. **By itself it does nothing** — it
//!    only exists so the [`Aggregate`] derive macro (when it grows in
//!    cycle-21 / L4.D to also scan `impl` blocks) can discover handler
//!    methods. V1 of `#[derive(Aggregate)]` emits a single combined
//!    `apply()` body via `match` on `event.event_type()`, with the
//!    aggregate's `apply_*` methods invoked by name.
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L4B-1** — Attribute syntax is `#[handles_event("npc.said")]`
//!   (rustc-idiomatic; supports multiple via stacking).
//!
//! ## Hand-written contract for `#[derive(Aggregate)]`
//!
//! The struct MUST have:
//!   * A field named `id` of type `String` (or any `AsRef<str>` — the macro
//!     emits `self.id.as_ref()` at call sites).
//!   * A field named `version` of type `u64`.
//!   * An optional `#[aggregate_type = "..."]` outer attribute. If omitted,
//!     the macro lowercases the struct ident (`World -> "world"`).
//!
//! The generated impl:
//!
//! ```ignore
//! impl dp_kernel::Aggregate for World {
//!     fn apply(&mut self, env: &dp_kernel::EventEnvelope) -> Result<(), String> {
//!         self.version = env.aggregate_version;
//!         Ok(())
//!     }
//!     fn aggregate_version(&self) -> u64 { self.version }
//! }
//! impl dp_kernel::AggregateMeta for World {
//!     fn aggregate_type() -> &'static str { "world" }
//!     fn id(&self) -> &str { self.id.as_ref() }
//! }
//! ```
//!
//! V1 of the apply() body is intentionally minimal — just version-bump —
//! because the goal of L4.B is to ship the trait-impl skeleton + attribute
//! parsing. The actual per-event-type dispatch is opt-in via concrete
//! `apply_<event_type>(&mut self, env)` methods the user writes by hand.
//! Cycle 21 (L4.D / per-aggregate macros) will extend the derive to emit
//! the dispatch automatically.
//!
//! ## What is NOT in cycle 17
//!
//! - **`#[derive(Projection)]`** — deferred to L4.D macros refinement
//!   (cycle 21). Projection trait usage is hand-written today.
//! - **Auto-dispatch from `#[handles_event]`** — the attribute is
//!   recognized + accepted to keep service code forward-compat, but its
//!   metadata is not yet wired into the derive macro's codegen.
//! - **Compile-error UI snapshots** — `trybuild` skeleton is ready in the
//!   test dir; full UI files land in cycle 21 alongside auto-dispatch.

use proc_macro::TokenStream;
use proc_macro2::TokenStream as TokenStream2;
use quote::{format_ident, quote};
use syn::{parse_macro_input, Data, DeriveInput, Fields, LitStr};

mod attrs;

/// `#[derive(Aggregate)]` — emits impls of `dp_kernel::Aggregate` and
/// `dp_kernel::AggregateMeta` for the annotated struct.
///
/// See crate-level docs for the field-shape contract.
#[proc_macro_derive(Aggregate, attributes(aggregate_type))]
pub fn derive_aggregate(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    match expand_derive_aggregate(&input) {
        Ok(ts) => ts.into(),
        Err(e) => e.to_compile_error().into(),
    }
}

/// `#[handles_event("type")]` — informational attribute on methods inside
/// an aggregate's `impl` block.
///
/// V1: parses + validates the attribute payload so misspellings surface as
/// nice errors. Does NOT alter the method body. Cycle 21 will wire the
/// payload into the derive macro's auto-dispatch.
///
/// Supports multiple invocations per method:
///
/// ```ignore
/// impl Counter {
///     #[handles_event("counter.incremented")]
///     #[handles_event("counter.decremented")]
///     fn apply_delta(&mut self, env: &EventEnvelope) -> Result<(), String> { … }
/// }
/// ```
#[proc_macro_attribute]
pub fn handles_event(attr: TokenStream, item: TokenStream) -> TokenStream {
    // Parse the literal string for validation (rejects `#[handles_event(42)]`
    // or `#[handles_event = "x"]` with helpful errors). The payload is then
    // discarded — V1 doesn't yet wire it into codegen.
    let parsed = syn::parse::<LitStr>(attr);
    if let Err(mut e) = parsed {
        e.combine(syn::Error::new(
            proc_macro2::Span::call_site(),
            "expected #[handles_event(\"event.type\")] (Q-L4B-1)",
        ));
        // Return the original item plus the compile error so cascading
        // failures (the user's `apply_*` method) stay visible.
        let item_ts: TokenStream2 = item.into();
        let err = e.to_compile_error();
        return quote! { #err #item_ts }.into();
    }
    // Validated — pass the method through untouched (V1 informational).
    item
}

fn expand_derive_aggregate(input: &DeriveInput) -> syn::Result<TokenStream2> {
    let name = &input.ident;

    // ── Validate struct shape ─────────────────────────────────────────────
    let Data::Struct(ds) = &input.data else {
        return Err(syn::Error::new_spanned(
            name,
            "#[derive(Aggregate)] only supports structs",
        ));
    };
    let Fields::Named(fields) = &ds.fields else {
        return Err(syn::Error::new_spanned(
            name,
            "#[derive(Aggregate)] requires named fields (id: String, version: u64)",
        ));
    };
    let mut has_id = false;
    let mut has_version = false;
    for f in &fields.named {
        if let Some(ident) = &f.ident {
            if ident == "id" {
                has_id = true;
            }
            if ident == "version" {
                has_version = true;
            }
        }
    }
    if !has_id {
        return Err(syn::Error::new_spanned(
            name,
            "#[derive(Aggregate)] requires a field named `id` (used for AggregateMeta::id)",
        ));
    }
    if !has_version {
        return Err(syn::Error::new_spanned(
            name,
            "#[derive(Aggregate)] requires a field named `version: u64` (used for Aggregate::aggregate_version)",
        ));
    }

    // ── Resolve aggregate_type ────────────────────────────────────────────
    //
    // Default: lowercase the struct name. Override via
    // `#[aggregate_type = "world"]` outer attribute.
    let agg_type = attrs::aggregate_type_for(input)?;

    // ── Emit ──────────────────────────────────────────────────────────────
    //
    // We use ::dp_kernel as the canonical path so the macro works whether
    // the caller imported via `use dp_kernel as kern;` or anything else.
    //
    // The `apply()` body in V1 is the version-bump skeleton. Concrete event
    // dispatch is the user's responsibility (write a wrapper method that
    // matches on `env.event_type` and then calls `aggregate.apply(env)?`
    // to bump version). Cycle 21 will fold the dispatch into the macro.
    let krate = format_ident!("dp_kernel");
    let agg_type_lit = LitStr::new(&agg_type, name.span());

    Ok(quote! {
        #[automatically_derived]
        impl ::#krate::Aggregate for #name {
            fn apply(&mut self, env: &::#krate::EventEnvelope) -> ::core::result::Result<(), ::std::string::String> {
                self.version = env.aggregate_version;
                ::core::result::Result::Ok(())
            }
            fn aggregate_version(&self) -> u64 {
                self.version
            }
        }
        #[automatically_derived]
        impl ::#krate::AggregateMeta for #name {
            fn aggregate_type() -> &'static str {
                #agg_type_lit
            }
            fn id(&self) -> &str {
                // `self.id` is required to be a String (or AsRef<str>);
                // we go through AsRef<str> so both work.
                ::core::convert::AsRef::<str>::as_ref(&self.id)
            }
        }
    })
}
