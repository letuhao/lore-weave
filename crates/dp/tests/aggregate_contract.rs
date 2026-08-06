//! **ONE aggregate name binds ONE tier and ONE scope — checked against a real
//! Rust AST.**
//!
//! # Why this file exists, and why it replaces a regex
//!
//! `V1-F1` established that the type system cannot hold this property: each
//! monomorphisation is individually consistent and the contradiction lives
//! *across* them, which is the one comparison a type checker never makes. The
//! conclusion drawn from that was *"so check it over the source"*, and
//! `scripts/dp-aggregate-gate.py` did — with a hand-rolled lexer in Python.
//!
//! **Three rounds of cold-start refutation then broke that lexer eleven times,
//! and the last round is the one that settles it.** Round 3's verdict, verbatim:
//!
//! > R6's closure argument is sound as a statement about Rust; its three
//! > implementations are not. *"What the impl binds"* is `impl_generics()`,
//! > which drops parameters two ways; *"the right-hand side of `type Tier`"* is
//! > a `re.search` over text that still contains string literals; *"the impl
//! > exists"* is a hand-rolled lexer that does not know one Rust literal form.
//!
//! Concretely, all four compiled, ran, and passed the gate:
//!
//! * `impl<F: Fn() -> u8, T2: Tier> ..` — `_balanced` counts the `>` of `->` as
//!   the closing angle bracket, so `T2` is never recorded as a parameter.
//! * `impl<r#T2: Tier, ..>` — a raw identifier fails `[A-Za-z_][A-Za-z0-9_]*`
//!   and the parameter is dropped.
//! * `#[doc = "type Tier = T2;"]` above the real `type Tier = T;` — the regex
//!   takes the FIRST match and reads the decoy.
//! * `cr#"unterminated quote: "tier"#` — C-string literals (stable since 1.77)
//!   are not in the lexer's raw-string branch, so the quote parity desyncs and
//!   the whole impl **vanishes silently**.
//!
//! Every one of those is a fact about *Rust's grammar* that a partial reimplementation
//! of that grammar got wrong. Patching the eleventh is not a strategy; the
//! seventh already wasn't. **So the property is checked where the grammar is
//! already correct: `syn`, the parser the Rust ecosystem uses.** A doc attribute
//! is an `Attribute`, not text that happens to contain `type Tier`. `r#T2` and
//! `T2` are the same `Ident`. `cr#".."#` is a `LitCStr`. `Fn() -> u8` is a
//! `TypeBareFn` inside a `TraitBound`. None of it needs a special case.
//!
//! # What this still cannot do, stated because the last three rounds were about
//! claims outrunning checks
//!
//! `syn` parses **syntax**, not **name resolution**. `type T2 = dp::T3;` is
//! syntactically a type alias whose right-hand side is a path; only the compiler
//! knows that `T2` at a use site resolves to `T3`. `R8` below covers the three
//! spellings that have been demonstrated — a `use .. as ..` rename, a braced
//! `use dp::{T3 as T2}`, and a `type` alias — by refusing to let any of them
//! *take a taxonomy name*, anywhere in the workspace. That is a real rule and it
//! is not the same as resolution.
//!
//! **The property's real home remains `dp-clippy`**, a lint running after name
//! resolution, which `06_data_plane/` has named as one of its three crates since
//! April and which does not exist: `D-DP-CLIPPY-NOT-BUILT`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use syn::visit::Visit;

/// The one excluded directory: `trybuild` fixtures exist in order NOT to
/// compile. Anchored and repo-relative — it was an unanchored substring
/// (`"tests/ui/"`, which matches `src/tests/ui/mod.rs` in any crate) until
/// `R2-5`.
const FIXTURE_DIR: &str = "crates/dp/tests/ui/";

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("repo root")
}

/// Every `.rs` file git would let you commit — tracked, plus untracked that is
/// not ignored. The same scope `no-absolute-host-paths` uses, and for the same
/// reason: the subject is *code that could reach a commit*, and a `rglob` walk
/// includes generated output that never can.
fn committable_rs(root: &Path) -> Vec<PathBuf> {
    let out = Command::new("git")
        .args(["ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.rs"])
        .current_dir(root)
        .output()
        .expect("git ls-files");
    assert!(out.status.success(), "git ls-files failed");
    String::from_utf8_lossy(&out.stdout)
        .split('\0')
        .filter(|s| !s.is_empty())
        .map(|s| root.join(s))
        .filter(|p| p.is_file())
        .collect()
}

fn rel(root: &Path, p: &Path) -> String {
    p.strip_prefix(root)
        .unwrap_or(p)
        .to_string_lossy()
        .replace('\\', "/")
}

// ─────────────────────────────────────────────────────────────────────────────
// The closed sets, read from their own definition sites
// ─────────────────────────────────────────────────────────────────────────────

/// First argument of every `declare_tier!` / `declare_scope!` invocation.
///
/// Delimiter-agnostic by construction: `syn` gives a `Macro` whose `delimiter`
/// is data, so `declare_tier!{..}` and `declare_tier!(..)` are the same item.
/// The Python gate hard-coded `\(` and a refuter minted a fifth tier by changing
/// one character (`R3-M2`).
struct DeclCollector {
    macro_name: &'static str,
    found: Vec<String>,
}

impl<'ast> Visit<'ast> for DeclCollector {
    fn visit_item_macro(&mut self, m: &'ast syn::ItemMacro) {
        if m.mac.path.is_ident(self.macro_name) {
            if let Some(first) = m.mac.tokens.clone().into_iter().next() {
                let t = first.to_string();
                if !t.is_empty() && t != "$" {
                    self.found.push(t);
                }
            }
        }
        syn::visit::visit_item_macro(self, m);
    }
}

fn declared(root: &Path, file: &str, macro_name: &'static str) -> Vec<String> {
    let src = std::fs::read_to_string(root.join(file)).expect(file);
    let ast = syn::parse_file(&src).unwrap_or_else(|e| panic!("{file} does not parse: {e}"));
    let mut c = DeclCollector { macro_name, found: Vec::new() };
    c.visit_file(&ast);
    c.found
}

// ─────────────────────────────────────────────────────────────────────────────
// The scan
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug)]
struct Finding {
    rule: &'static str,
    where_: String,
    detail: String,
}

/// Every identifier appearing anywhere in a type — including inside generic
/// arguments, qualified paths, tuples, references and bare-fn signatures.
///
/// This is what makes `R6` a rule about the *type* rather than about its
/// spelling: `Wrapper<T>`, `<Self as Pick>::Out` and `(T, u8)` all surface `T`
/// or `Self` without any per-shape special case.
struct IdentSink(Vec<String>);

impl<'ast> Visit<'ast> for IdentSink {
    fn visit_ident(&mut self, i: &'ast proc_macro2::Ident) {
        // `Ident::to_string()` on a raw identifier yields `r#T2`; strip the
        // prefix so `r#T2` and `T2` compare equal, as they do to rustc (`R3-B3`).
        self.0.push(i.to_string().trim_start_matches("r#").to_string());
    }
}

fn idents_of(ty: &syn::Type) -> Vec<String> {
    let mut s = IdentSink(Vec::new());
    s.visit_type(ty);
    s.0
}

fn last_segment(ty: &syn::Type) -> String {
    match ty {
        syn::Type::Path(p) => p
            .path
            .segments
            .last()
            .map(|s| {
                // Keep generic args attached, so `Wrapper<T>` cannot pass a
                // membership test that `Wrapper` alone would.
                if matches!(s.arguments, syn::PathArguments::None) {
                    s.ident.to_string().trim_start_matches("r#").to_string()
                } else {
                    format!("{}<..>", s.ident)
                }
            })
            .unwrap_or_default(),
        _ => String::new(),
    }
}

struct ImplCollector<'a> {
    root: &'a Path,
    file: &'a Path,
    src: &'a str,
    tiers: &'a [String],
    scopes: &'a [String],
    taxonomy: Vec<String>,
    findings: Vec<Finding>,
    names: &'a mut BTreeMap<String, String>,
    impls: usize,
}

impl<'a> ImplCollector<'a> {
    fn at(&self, span: proc_macro2::Span) -> String {
        format!("{}:{}", rel(self.root, self.file), span.start().line)
    }

    fn push(&mut self, rule: &'static str, span: proc_macro2::Span, detail: String) {
        let where_ = self.at(span);
        self.findings.push(Finding { rule, where_, detail });
    }
}

impl<'ast, 'a> Visit<'ast> for ImplCollector<'a> {
    fn visit_item_macro(&mut self, m: &'ast syn::ItemMacro) {
        // `R10` — one body, N invocations. `syn` parses a `macro_rules!` body as
        // opaque tokens, so an impl inside it is invisible to `visit_item_impl`
        // by construction; that is correct, and it is also exactly why the body
        // must be REFUSED rather than skipped.
        if m.mac.path.is_ident("macro_rules")
            && m.mac.tokens.to_string().contains("DpAggregate")
        {
            self.impls += 1;
            self.push(
                "R10",
                m.mac.path.segments[0].ident.span(),
                "an `impl DpAggregate` inside a `macro_rules!` body: one body emits N impls, and \
                 this check can only see the body. Write the impls out, or give the macro a \
                 single invocation site"
                    .into(),
            );
        }
        syn::visit::visit_item_macro(self, m);
    }

    fn visit_item_use(&mut self, u: &'ast syn::ItemUse) {
        // `R8` — an alias may not TAKE a taxonomy name. Covers `use dp::T3 as
        // T2;` and the braced `use dp::{T3 as T2};` identically, because `syn`
        // gives the same `UseRename` node for both (`R3-M1`).
        struct Renames<'b>(&'b [String], Vec<(String, proc_macro2::Span)>);
        impl<'ast, 'b> Visit<'ast> for Renames<'b> {
            fn visit_use_rename(&mut self, r: &'ast syn::UseRename) {
                let to = r.rename.to_string().trim_start_matches("r#").to_string();
                if self.0.contains(&to) {
                    self.1.push((to, r.rename.span()));
                }
            }
        }
        let mut r = Renames(&self.taxonomy, Vec::new());
        r.visit_item_use(u);
        for (name, span) in r.1 {
            self.push(
                "R8",
                span,
                format!(
                    "`use .. as {name}` renames something to a taxonomy name. Every membership \
                     check then reads {name:?} and reports the WRONG tier or scope — and under \
                     `#[cfg(..)]` it becomes a build-time switch, which DP-A9 forbids: a tier is \
                     'not switchable without a design-change'"
                ),
            );
        }
        syn::visit::visit_item_use(self, u);
    }

    fn visit_item_type(&mut self, t: &'ast syn::ItemType) {
        // `R8`, the other spelling: `type T2 = dp::T3;` (`R3-M1`).
        let name = t.ident.to_string().trim_start_matches("r#").to_string();
        if self.taxonomy.contains(&name) {
            self.push(
                "R8",
                t.ident.span(),
                format!(
                    "`type {name} = ..` gives a taxonomy name to something else. The check would \
                     then read {name:?} and name the wrong tier or scope with full confidence"
                ),
            );
        }
        syn::visit::visit_item_type(self, t);
    }

    fn visit_item_impl(&mut self, i: &'ast syn::ItemImpl) {
        let is_dp = i
            .trait_
            .as_ref()
            .and_then(|(path, _)| path.segments.last())
            .is_some_and(|s| s.ident == "DpAggregate");
        if !is_dp {
            syn::visit::visit_item_impl(self, i);
            return;
        }
        self.impls += 1;

        // What the impl BINDS. `syn::Generics` is the real list — no bracket
        // counting, so an `Fn() -> u8` bound cannot truncate it (`R3-B2`), and
        // raw identifiers are `Ident`s like any other (`R3-B3`).
        let bound: Vec<String> = i
            .generics
            .type_params()
            .map(|p| p.ident.to_string().trim_start_matches("r#").to_string())
            .chain(
                i.generics
                    .const_params()
                    .map(|p| p.ident.to_string().trim_start_matches("r#").to_string()),
            )
            .collect();

        // `R7` — a parameter may not be NAMED after a taxonomy member.
        for g in &bound {
            if self.taxonomy.contains(g) {
                self.push(
                    "R7",
                    i.impl_token.span,
                    format!(
                        "generic parameter `{g}` shadows the taxonomy name `{g}`. `type Tier = \
                         {g}` then LOOKS concrete and is not — V1-F1 restored by a one-character \
                         rename, and the likeliest accidental recurrence"
                    ),
                );
            }
        }

        let assoc: BTreeMap<String, &syn::ImplItemType> = i
            .items
            .iter()
            .filter_map(|it| match it {
                syn::ImplItem::Type(t) => Some((t.ident.to_string(), t)),
                _ => None,
            })
            .collect();

        for (rule, name, legal) in [
            ("R1", "Tier", self.tiers),
            ("R2", "Scope", self.scopes),
        ] {
            let Some(t) = assoc.get(name) else {
                self.push(
                    rule,
                    i.impl_token.span,
                    format!("no `type {name} = ..;` in this impl — which {} does it bind?",
                            name.to_lowercase()),
                );
                continue;
            };

            // `R6` — THE load-bearing rule, and the reason it is a closure
            // argument rather than a pattern list: to be generic, the right-hand
            // side MUST name something in scope, and the only things in scope
            // are the impl's parameters and `Self`.
            let ids = idents_of(&t.ty);
            let mut named: Vec<&str> = bound
                .iter()
                .filter(|g| ids.iter().any(|i| i == *g))
                .map(String::as_str)
                .collect();
            if ids.iter().any(|i| i == "Self") {
                named.push("Self");
            }
            if !named.is_empty() {
                let list = named
                    .iter()
                    .map(|n| format!("`{n}`"))
                    .collect::<Vec<_>>()
                    .join(", ");
                self.push(
                    "R6",
                    t.ident.span(),
                    format!(
                        "`type {name}` names {list}, which this impl binds. One aggregate name \
                         then carries several {}s, chosen by the caller per request — DP-A9: a \
                         tier is design-time, 'not configurable per player'",
                        name.to_lowercase()
                    ),
                );
                continue;
            }

            let seg = last_segment(&t.ty);
            if !legal.iter().any(|l| *l == seg) {
                self.push(
                    rule,
                    t.ident.span(),
                    format!(
                        "`type {name} = {seg}` does not name a declared {} ({})",
                        name.to_lowercase(),
                        legal.join(", ")
                    ),
                );
            }
        }

        // `R3` / `R4` — the cache-key token. A real `ImplItemConst`, so a
        // `#[doc]` attribute above it is an `Attribute` and cannot be read
        // instead (`R3-B1`), and `LitStr::value()` decodes escapes exactly as
        // rustc does, so `"walle\u{74}"` IS `"wallet"` (`R2-7`).
        let konst = i.items.iter().find_map(|it| match it {
            syn::ImplItem::Const(c) if c.ident == "TYPE_NAME" => Some(c),
            _ => None,
        });
        let Some(c) = konst else {
            self.push("R3", i.impl_token.span, "no `const TYPE_NAME` in this impl".into());
            syn::visit::visit_item_impl(self, i);
            return;
        };
        let lit = match &c.expr {
            syn::Expr::Lit(syn::ExprLit { lit: syn::Lit::Str(s), .. }) => Some(s.value()),
            _ => None,
        };
        let Some(value) = lit else {
            self.push(
                "R3",
                c.ident.span(),
                "`TYPE_NAME` is not a string literal. It is the aggregate token of the DP-Ch5 \
                 cache key: a computed name cannot be read without running the program, and \
                 cannot be checked for collisions at all"
                    .into(),
            );
            syn::visit::visit_item_impl(self, i);
            return;
        };

        // `DpAggregate::TYPE_NAME`'s own doc says snake_case and stable. The
        // second half is not checkable here; the first is, and was checked by
        // nothing (`R3-NIT`).
        if !value.is_empty()
            && !value
                .chars()
                .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_')
        {
            self.push(
                "R11",
                c.ident.span(),
                format!(
                    "TYPE_NAME {value:?} is not snake_case. Its own doc requires it, and it is a \
                     cache-key token: a stray capital or space makes two spellings of one \
                     aggregate"
                ),
            );
        }

        let here = self.at(c.ident.span());
        if let Some(prev) = self.names.get(&value) {
            let prev = prev.clone();
            self.push(
                "R4",
                c.ident.span(),
                format!(
                    "TYPE_NAME {value:?} is already bound at {prev}. Two impls under one name = \
                     two cache entries for one logical aggregate, under two coherency contracts \
                     (REC-102c's survives_store_outage among them). Compared by DECODED value, \
                     because rustc does"
                ),
            );
        } else {
            self.names.insert(value, here);
        }

        let _ = self.src;
        syn::visit::visit_item_impl(self, i);
    }
}

// ─────────────────────────────────────────────────────────────────────────────

fn scan(root: &Path, files: &[PathBuf], tiers: &[String], scopes: &[String])
    -> (Vec<Finding>, usize)
{
    let mut findings = Vec::new();
    let mut names: BTreeMap<String, String> = BTreeMap::new();
    let mut impls = 0usize;
    let taxonomy: Vec<String> = tiers.iter().chain(scopes.iter()).cloned().collect();

    for f in files {
        let Ok(src) = std::fs::read_to_string(f) else { continue };
        // Fast reject, and it is the only place a file is skipped without being
        // parsed. `R8`'s alias rules apply repo-wide, so a file may matter
        // without containing an impl (`R3-M1`, the cross-file alias).
        if !src.contains("DpAggregate") && !taxonomy.iter().any(|t| src.contains(t.as_str())) {
            continue;
        }
        let ast = match syn::parse_file(&src) {
            Ok(a) => a,
            Err(e) => {
                // FAIL CLOSED, and only for a file that is actually a subject.
                // The Python lexer `continue`d here, which is how one odd brace
                // in a doc string hid a live escape (`R2-4`, `R3-B4`).
                if src.contains("DpAggregate") {
                    findings.push(Finding {
                        rule: "R9",
                        where_: rel(root, f),
                        detail: format!(
                            "this file mentions `DpAggregate` and does not parse ({e}), so no rule \
                             below could be applied to it. A check that skips what it cannot read \
                             reports coverage it does not have"
                        ),
                    });
                }
                continue;
            }
        };
        let mut c = ImplCollector {
            root,
            file: f,
            src: &src,
            tiers,
            scopes,
            taxonomy: taxonomy.clone(),
            findings: Vec::new(),
            names: &mut names,
            impls: 0,
        };
        c.visit_file(&ast);
        impls += c.impls;
        findings.extend(c.findings);
    }
    (findings, impls)
}

/// The contract, over every `.rs` file that could reach a commit.
#[test]
fn one_aggregate_name_binds_one_tier_and_one_scope() {
    let root = repo_root();
    let tiers = declared(&root, "crates/dp/src/tier.rs", "declare_tier");
    let scopes = declared(&root, "crates/dp/src/scope.rs", "declare_scope");

    assert!(
        tiers.len() >= 4 && scopes.len() >= 2,
        "parsed {} tier(s) {tiers:?} and {} scope(s) {scopes:?}. DP-A5 closes the tier taxonomy at \
         four and DP-A14 the scope set at two; a short parse means the declaration shape moved and \
         every membership test below would compare against a truncated set",
        tiers.len(),
        scopes.len()
    );

    let all = committable_rs(&root);
    let (scanned, excluded): (Vec<_>, Vec<_>) =
        all.iter().cloned().partition(|p| !rel(&root, p).starts_with(FIXTURE_DIR));

    // The SCOPE is a set difference, not a count (`V2-F2`): everything excluded
    // must be under the one named directory. A count check passes while any
    // amount of the tree goes dark, so long as one subject survives.
    let stray: Vec<String> = excluded
        .iter()
        .map(|p| rel(&root, p))
        .filter(|r| !r.starts_with(FIXTURE_DIR))
        .collect();
    assert!(stray.is_empty(), "excluded files outside {FIXTURE_DIR}: {stray:?}");

    let (findings, impls) = scan(&root, &scanned, &tiers, &scopes);

    assert!(
        impls > 0,
        "no `impl DpAggregate` found in {} committable .rs file(s). A scan over nothing passes \
         trivially (NV-3)",
        scanned.len()
    );

    if !findings.is_empty() {
        let mut msg = format!(
            "\n{} finding(s) across {impls} `impl DpAggregate` block(s):\n\n",
            findings.len()
        );
        for f in &findings {
            msg.push_str(&format!("  {}  {}\n      {}\n", f.rule, f.where_, f.detail));
        }
        msg.push_str(
            "\nONE aggregate name binds ONE tier and ONE scope. The type system cannot check this\n\
             — each monomorphisation is individually consistent and the contradiction lives across\n\
             them. See V1-F1 / R2-* / R3-* in docs/plans/2026-08-06-game-tier-build-RUN-STATE.md.\n",
        );
        panic!("{msg}");
    }

    println!(
        "aggregate-contract: OK — {impls} `impl DpAggregate` block(s) in {} .rs file(s) \
         ({} trybuild fixture(s) excluded); every one binds one of {tiers:?} and one of \
         {scopes:?}, with a literal, unique, snake_case TYPE_NAME, and none reaches its tier \
         through a generic parameter, an alias or a macro body",
        scanned.len(),
        excluded.len()
    );
}
