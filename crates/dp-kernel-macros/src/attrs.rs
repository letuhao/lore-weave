//! Outer-attribute parsing for `#[derive(Aggregate)]`.
//!
//! Currently supports `#[aggregate_type = "world"]` which overrides the
//! default lowercased struct-name aggregate type.

use syn::{DeriveInput, Lit, Meta};

/// Resolve `aggregate_type` for an [`Aggregate`]-derived struct.
///
/// Default: lowercase the struct name (`World -> "world"`).
/// Override: `#[aggregate_type = "..."]` on the struct.
///
/// Errors if the attribute payload is not a string literal.
pub(crate) fn aggregate_type_for(input: &DeriveInput) -> syn::Result<String> {
    for attr in &input.attrs {
        if !attr.path().is_ident("aggregate_type") {
            continue;
        }
        // We accept both syntaxes:
        //   #[aggregate_type = "world"]   ← name-value form (preferred)
        //   #[aggregate_type("world")]    ← list form (tolerated)
        match &attr.meta {
            Meta::NameValue(nv) => {
                if let syn::Expr::Lit(syn::ExprLit { lit: Lit::Str(s), .. }) = &nv.value {
                    return Ok(s.value());
                }
                return Err(syn::Error::new_spanned(
                    &nv.value,
                    "#[aggregate_type] expects a string literal",
                ));
            }
            Meta::List(list) => {
                // Parse the body as a single Lit::Str.
                let parsed: syn::Result<syn::LitStr> = list.parse_args();
                return match parsed {
                    Ok(s) => Ok(s.value()),
                    Err(_) => Err(syn::Error::new_spanned(
                        list,
                        "#[aggregate_type(...)] body must be a string literal",
                    )),
                };
            }
            Meta::Path(_) => {
                return Err(syn::Error::new_spanned(
                    attr,
                    "#[aggregate_type] requires a value, e.g. #[aggregate_type = \"world\"]",
                ));
            }
        }
    }
    // Default: lowercase the struct name.
    Ok(input.ident.to_string().to_lowercase())
}
