//! Level-0 flat-world sketch: draw `n` random tectonic-plate polygons on a
//! `width × height` rectangle (void = near-black between them). All flat — no
//! elevation yet.
//!
//! Run:
//!   cargo run --release -p world-gen --example flatworld
//!   cargo run --release -p world-gen --example flatworld -- \
//!       --width 1280 --height 720 --plates 7 --seed 3 --out flat.png
//!
//! Every knob in `FlatParams` is exposed as a flag; see `--help` is *not*
//! wired (this is a thin sketch), so the flags below are the contract.

use std::path::PathBuf;
use world_gen::flatworld::{
    export, generate, render_height_rgb, render_rgb, render_zones_rgb, FlatParams,
};
use world_gen::ErosionStrength;
use world_gen::flat_climate::{export_zone_climates, HemisphereLayout, WorldClimateParams};
use world_gen::zonegen::{
    render_all_zones, render_all_zones_biome, render_all_zones_eroded, render_zone, zone_height,
    ClassRatios, TerrainClass,
};

fn main() {
    let mut p = FlatParams::default();
    // v4.3d: optional model override for any of the --llm-* flags.
    let mut llm_model: Option<String> = None;
    let mut out = PathBuf::from("flatworld.png");
    // Optional second output: grayscale elevation (void dark → collisions white).
    let mut height_out: Option<PathBuf> = None;
    // Optional third output: interior-zone subdivision per plate.
    let mut zones_out: Option<PathBuf> = None;
    // Optional data export: the plate/zone anchor JSON for per-zone terrain gen.
    let mut data_out: Option<PathBuf> = None;
    // Optional single-zone local terrain: "plate_id,zone_id" + output path.
    let mut zone_sel: Option<(usize, usize)> = None;
    let mut zone_terrain_out: Option<PathBuf> = None;
    // Optional full-map terrain: every zone rendered together (hypsometric).
    let mut all_zones_out: Option<PathBuf> = None;
    // Optional class-comparison demo: the 4 classes side by side, same scale.
    let mut class_demo_out: Option<PathBuf> = None;
    // Optional eroded full-map terrain (B2) + erosion strength.
    let mut eroded_out: Option<PathBuf> = None;
    let mut erosion = ErosionStrength::Moderate;
    // Optional B5 v2 biome-coloured terrain + climate knobs.
    let mut biome_out: Option<PathBuf> = None;
    // Optional v4 sidecar: per-zone climate JSON for law-based eval.
    let mut climate_out: Option<PathBuf> = None;
    let mut climate = WorldClimateParams::default();
    // Whether the user overrode continentality_reach explicitly (skip auto-scale).
    let mut reach_explicit = false;

    // **Civ Ship 7d**: opt-in civ-layer output paths + naming provider.
    // None of these set → civ-layer pipeline doesn't run.
    let mut civ_png_out: Option<PathBuf> = None;
    let mut civ_svg_out: Option<PathBuf> = None;
    let mut civ_json_out: Option<PathBuf> = None;
    let mut civ_seed: u64 = 42;
    let mut civ_ocean_target: usize = 64;
    let mut civ_culture_count: u8 = 5;
    let mut civ_density = world_gen::creative_seed::SettlementDensity::Medium;
    let mut civ_archetype: String = "HighFantasy".to_string();
    // Naming source: None → synthetic; Some(kind) → real LLM TextProvider.
    #[derive(Clone, Copy)]
    enum NameSource { Synthetic, Anthropic, OpenAI, Ollama, LmStudio }
    let mut name_source = NameSource::Synthetic;
    let mut name_model: Option<String> = None;

    // Minimal hand-rolled arg parsing (`--flag value`), to keep the sketch
    // dependency-free of the main CLI.
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        let flag = args[i].as_str();
        let val = args.get(i + 1).cloned();
        let need = || val.clone().unwrap_or_else(|| panic!("{flag} needs a value"));
        // **Ship 7e fix**: pre-existing bug — loop unconditionally
        // advanced `i += 2`, so a valueless flag (the `--name-*`
        // provider flags) silently ate the next arg. Flag arms that
        // don't consume a value set `valueless = true`; loop advance
        // becomes conditional.
        let mut valueless = false;
        match flag {
            "--width" => p.width = need().parse().expect("width"),
            "--height" => p.height = need().parse().expect("height"),
            "--plates" => p.plate_count = need().parse().expect("plates"),
            "--seed" => p.seed = need().parse().expect("seed"),
            "--min-verts" => p.min_vertices = need().parse().expect("min-verts"),
            "--max-verts" => p.max_vertices = need().parse().expect("max-verts"),
            "--min-radius" => p.min_radius_frac = need().parse().expect("min-radius"),
            "--max-radius" => p.max_radius_frac = need().parse().expect("max-radius"),
            "--jitter" => p.edge_jitter = need().parse().expect("jitter"),
            "--max-speed" => p.max_speed = need().parse().expect("max-speed"),
            "--collision-gain" => p.collision_gain = need().parse().expect("collision-gain"),
            "--separation" => p.separation = need().parse().expect("separation"),
            "--min-zones" => p.min_zones = need().parse().expect("min-zones"),
            "--max-zones" => p.max_zones = need().parse().expect("max-zones"),
            "--coastline-roughness" => {
                p.coastline.roughness = need().parse().expect("coastline-roughness 0..1");
            }
            "--coastline-iter" => {
                p.coastline.iterations = need().parse().expect("coastline-iter 0..5");
            }
            "--coastline-enabled" => {
                // 0 = disabled, anything else = use existing roughness/iter knobs.
                let v: u32 = need().parse().expect("coastline-enabled 0|1");
                if v == 0 {
                    p.coastline = world_gen::shape::FractalizeConfig::disabled();
                }
            }
            "--force-kind" => {
                let kind = match need().as_str() {
                    "ellipse" => world_gen::shape::ShapeKind::Ellipse,
                    "bezier" => world_gen::shape::ShapeKind::BezierSpine,
                    "polar" => world_gen::shape::ShapeKind::Polar,
                    "boolean" => world_gen::shape::ShapeKind::Boolean,
                    "sdf" => world_gen::shape::ShapeKind::SdfCapsuleChain,
                    "marching" => world_gen::shape::ShapeKind::MarchingNoise,
                    "slime" => world_gen::shape::ShapeKind::Slime,
                    "stamp" => world_gen::shape::ShapeKind::Stamp,
                    other => panic!("unknown --force-kind {other}"),
                };
                p.plate_dispatch = Some(world_gen::shape::DispatchMode::Fixed(kind));
            }
            // **v4.3d** opt-in LLM dispatch. Pick exactly one of these
            // three flags; `--llm-model` overrides the provider default.
            // API keys come from env vars; Ollama doesn't need one.
            "--llm-anthropic" => {
                use std::sync::Arc;
                use world_gen::shape::{
                    AnthropicProvider, DispatchMode, InMemoryDispatchCache,
                };
                let key = std::env::var("ANTHROPIC_API_KEY")
                    .expect("--llm-anthropic requires ANTHROPIC_API_KEY env var");
                let provider: Arc<dyn world_gen::shape::LlmProvider> = match llm_model.as_ref() {
                    Some(m) => Arc::new(AnthropicProvider::with_base_url(
                        key,
                        world_gen::shape::anthropic::DEFAULT_BASE_URL,
                        m,
                    )),
                    None => Arc::new(AnthropicProvider::new(key)),
                };
                let cache: Arc<dyn world_gen::shape::DispatchCache> =
                    Arc::new(InMemoryDispatchCache::new());
                // Layered([Llm, Weighted]) so transport / parse errors
                // fall through to the deterministic v3.6 default.
                p.plate_dispatch = Some(DispatchMode::Layered(vec![
                    DispatchMode::Llm { provider, cache },
                    DispatchMode::Weighted(world_gen::shape::engine_v3_6_weights()),
                ]));
            }
            "--llm-openai" => {
                use std::sync::Arc;
                use world_gen::shape::{
                    DispatchMode, InMemoryDispatchCache, OpenAIProvider,
                };
                let key = std::env::var("OPENAI_API_KEY")
                    .expect("--llm-openai requires OPENAI_API_KEY env var");
                let provider: Arc<dyn world_gen::shape::LlmProvider> = match llm_model.as_ref() {
                    Some(m) => Arc::new(OpenAIProvider::with_base_url(
                        key,
                        world_gen::shape::openai::DEFAULT_BASE_URL,
                        m,
                    )),
                    None => Arc::new(OpenAIProvider::new(key)),
                };
                let cache: Arc<dyn world_gen::shape::DispatchCache> =
                    Arc::new(InMemoryDispatchCache::new());
                p.plate_dispatch = Some(DispatchMode::Layered(vec![
                    DispatchMode::Llm { provider, cache },
                    DispatchMode::Weighted(world_gen::shape::engine_v3_6_weights()),
                ]));
            }
            "--llm-ollama" => {
                use std::sync::Arc;
                use world_gen::shape::{
                    DispatchMode, InMemoryDispatchCache, OllamaProvider,
                };
                let model = llm_model
                    .clone()
                    .unwrap_or_else(|| world_gen::shape::ollama::DEFAULT_MODEL.to_string());
                let provider: Arc<dyn world_gen::shape::LlmProvider> =
                    Arc::new(OllamaProvider::new(model));
                let cache: Arc<dyn world_gen::shape::DispatchCache> =
                    Arc::new(InMemoryDispatchCache::new());
                p.plate_dispatch = Some(DispatchMode::Layered(vec![
                    DispatchMode::Llm { provider, cache },
                    DispatchMode::Weighted(world_gen::shape::engine_v3_6_weights()),
                ]));
            }
            "--llm-model" => llm_model = Some(need()),
            "--out" => out = PathBuf::from(need()),
            "--height-out" => height_out = Some(PathBuf::from(need())),
            "--zones-out" => zones_out = Some(PathBuf::from(need())),
            "--data-out" => data_out = Some(PathBuf::from(need())),
            "--zone" => {
                let v = need();
                let (a, b) = v.split_once(',').expect("--zone wants plate,zone");
                zone_sel = Some((a.parse().expect("plate id"), b.parse().expect("zone id")));
            }
            "--zone-terrain-out" => zone_terrain_out = Some(PathBuf::from(need())),
            "--all-zones-out" => all_zones_out = Some(PathBuf::from(need())),
            "--class-demo" => class_demo_out = Some(PathBuf::from(need())),
            "--eroded-out" => eroded_out = Some(PathBuf::from(need())),
            "--erosion" => {
                erosion = match need().as_str() {
                    "none" => ErosionStrength::None,
                    "light" => ErosionStrength::Light,
                    "moderate" => ErosionStrength::Moderate,
                    "heavy" => ErosionStrength::Heavy,
                    other => panic!("unknown erosion strength: {other}"),
                }
            }
            "--biome-out" => biome_out = Some(PathBuf::from(need())),
            "--climate-out" => climate_out = Some(PathBuf::from(need())),
            "--hemisphere" => {
                climate.hemisphere_layout = match need().as_str() {
                    "equatorial" => HemisphereLayout::Equatorial,
                    "north" => HemisphereLayout::NorthOnly,
                    "south" => HemisphereLayout::SouthOnly,
                    other => panic!("unknown hemisphere: {other} (expected equatorial|north|south)"),
                }
            }
            "--t-eq" => climate.t_eq = need().parse().expect("t-eq"),
            "--t-pole" => climate.t_pole = need().parse().expect("t-pole"),
            "--precip-eq" => climate.precip_eq = need().parse().expect("precip-eq"),
            "--precip-subtropic" => climate.precip_subtropic = need().parse().expect("precip-subtropic"),
            "--precip-midlat" => climate.precip_midlat = need().parse().expect("precip-midlat"),
            "--precip-polar" => climate.precip_polar = need().parse().expect("precip-polar"),
            "--continentality-reach" => {
                climate.continentality_reach = need().parse().expect("continentality-reach");
                reach_explicit = true;
            }
            "--continentality-atten" => {
                climate.continentality_precip_atten = need().parse().expect("continentality-atten");
            }
            "--lapse" => climate.lapse_per_elev_unit = need().parse().expect("lapse"),
            "--ice-temp" => climate.ice_temp = need().parse().expect("ice-temp"),
            "--tundra-temp" => climate.tundra_temp = need().parse().expect("tundra-temp"),
            // **Civ Ship 7d** civ-layer flags.
            "--civ-png-out" => civ_png_out = Some(PathBuf::from(need())),
            "--civ-svg-out" => civ_svg_out = Some(PathBuf::from(need())),
            "--civ-json-out" => civ_json_out = Some(PathBuf::from(need())),
            "--civ-seed" => civ_seed = need().parse().expect("civ-seed"),
            "--civ-ocean-target" => civ_ocean_target = need().parse().expect("civ-ocean-target"),
            "--civ-culture-count" => civ_culture_count = need().parse().expect("civ-culture-count"),
            "--civ-density" => {
                use world_gen::creative_seed::SettlementDensity;
                civ_density = match need().as_str() {
                    "sparse" => SettlementDensity::Sparse,
                    "medium" => SettlementDensity::Medium,
                    "dense" => SettlementDensity::Dense,
                    other => panic!("unknown --civ-density {other}; want sparse|medium|dense"),
                };
            }
            "--civ-archetype" => civ_archetype = need(),
            "--name-anthropic" => { name_source = NameSource::Anthropic; valueless = true; }
            "--name-openai" => { name_source = NameSource::OpenAI; valueless = true; }
            "--name-ollama" => { name_source = NameSource::Ollama; valueless = true; }
            "--name-lmstudio" => { name_source = NameSource::LmStudio; valueless = true; }
            "--name-model" => name_model = Some(need()),
            other => panic!("unknown flag: {other}"),
        }
        i += if valueless { 1 } else { 2 };
    }

    let world = generate(&p);
    let rgb = render_rgb(&world);
    image::save_buffer(
        &out,
        &rgb,
        world.width,
        world.height,
        image::ExtendedColorType::Rgb8,
    )
    .expect("failed to write PNG");

    println!(
        "wrote {} — {}×{}, {} plates (seed {})",
        out.display(),
        world.width,
        world.height,
        world.plates.len(),
        p.seed
    );

    if let Some(hpath) = height_out {
        let (height_rgb, max_e) = render_height_rgb(&world);
        image::save_buffer(
            &hpath,
            &height_rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write height PNG");
        println!("wrote {} — elevation (max {max_e:.3})", hpath.display());
    }

    if let Some(zpath) = zones_out {
        let zones_rgb = render_zones_rgb(&world);
        image::save_buffer(
            &zpath,
            &zones_rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write zones PNG");
        let total: usize = world.plates.iter().map(|p| p.zones.len()).sum();
        println!("wrote {} — {} zones across {} plates", zpath.display(), total, world.plates.len());
    }

    if let Some(dpath) = data_out {
        let data = export(&world, p.seed);
        let json = serde_json::to_string_pretty(&data).expect("serialize world data");
        std::fs::write(&dpath, json).expect("failed to write data JSON");
        let zones: usize = data.plates.iter().map(|pl| pl.zones.len()).sum();
        println!(
            "wrote {} — {} plates / {} zones (anchor data)",
            dpath.display(),
            data.plates.len(),
            zones
        );
    }

    if let Some(cpath) = class_demo_out {
        // Render the 4 classes as side-by-side panels over the SAME coordinate
        // field, base, and seed, normalized on a SINGLE shared scale — so the
        // per-class relief difference is unambiguous (flat / rolling / raised /
        // jagged). A verification aid, not part of the world.
        let classes = [
            TerrainClass::Plains,
            TerrainClass::Hills,
            TerrainClass::Plateau,
            TerrainClass::Mountains,
        ];
        let panel = 256usize;
        let gap = 8usize;
        let ph = 256usize;
        let w = classes.len() * panel + (classes.len() - 1) * gap;
        let base = 0.40f32;
        let salt = 0x5EED_1234u32;

        // Pass 1: heights + shared range.
        let mut field = vec![f32::NAN; w * ph];
        let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
        for (ci, &class) in classes.iter().enumerate() {
            let x0 = ci * (panel + gap);
            for yy in 0..ph {
                for xx in 0..panel {
                    let h = zone_height(xx as f32, yy as f32, class, base, salt);
                    field[yy * w + (x0 + xx)] = h;
                    lo = lo.min(h);
                    hi = hi.max(h);
                }
            }
            let (mut clo, mut chi) = (f32::INFINITY, f32::NEG_INFINITY);
            for yy in 0..ph {
                for xx in 0..panel {
                    let h = field[yy * w + (x0 + xx)];
                    clo = clo.min(h);
                    chi = chi.max(h);
                }
            }
            println!(
                "  {:9} base={base:.2} relief=[{:.3},{:.3}] span={:.3}",
                class.name(),
                clo,
                chi,
                chi - clo
            );
        }
        let span = (hi - lo).max(1e-6);
        let mut rgb = vec![0u8; w * ph * 3];
        for i in 0..w * ph {
            let g = if field[i].is_nan() {
                0u8 // gap = black
            } else {
                (((field[i] - lo) / span).clamp(0.0, 1.0) * 255.0).round() as u8
            };
            rgb[i * 3] = g;
            rgb[i * 3 + 1] = g;
            rgb[i * 3 + 2] = g;
        }
        image::save_buffer(
            &cpath,
            &rgb,
            w as u32,
            ph as u32,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write class-demo PNG");
        println!(
            "wrote {} — class demo (Plains | Hills | Plateau | Mountains, shared scale)",
            cpath.display()
        );
    }

    if let Some(epath) = eroded_out {
        let rgb = render_all_zones_eroded(&world, p.seed, &ClassRatios::default(), erosion);
        image::save_buffer(
            &epath,
            &rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write eroded PNG");
        println!("wrote {} — eroded zone terrain ({erosion:?})", epath.display());
    }

    if let Some(bpath) = biome_out {
        // Auto-scale continentality_reach to mean plate radius (W14 fix) —
        // reach saturates at ~40 % of plate radius regardless of how many
        // plates or how big the map. Unless the user pinned reach explicitly.
        let cm = if reach_explicit {
            climate.clone()
        } else {
            climate
                .clone()
                .scaled_for(world.width, world.height, world.plates.len())
        };
        let rgb = render_all_zones_biome(&world, p.seed, &ClassRatios::default(), erosion, &cm);
        image::save_buffer(
            &bpath,
            &rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write biome PNG");
        println!(
            "wrote {} — B5 v2 biome terrain ({:?}, {erosion:?}, reach={:.0}px)",
            bpath.display(),
            cm.hemisphere_layout,
            cm.continentality_reach
        );
    }

    if let Some(cpath) = climate_out {
        // v4 law-based eval sidecar: per-zone climate (temp / precip / biome /
        // lat_dist). Uses the SAME compute_zone_climate the biome render uses,
        // so values match the painted pixels by construction.
        let cm = if reach_explicit {
            climate.clone()
        } else {
            climate
                .clone()
                .scaled_for(world.width, world.height, world.plates.len())
        };
        let export = export_zone_climates(&world, &cm);
        let json = serde_json::to_string_pretty(&export).expect("serialize climate export");
        std::fs::write(&cpath, json).expect("failed to write climate JSON");
        println!(
            "wrote {} — {} zones (per-zone climate sidecar)",
            cpath.display(),
            export.zones.len()
        );
    }

    if let Some(apath) = all_zones_out {
        let outline = apath
            .file_stem()
            .and_then(|s| s.to_str())
            .map(|s| s.ends_with("outlined"))
            .unwrap_or(false);
        let rgb = render_all_zones(&world, p.seed, &ClassRatios::default(), outline);
        image::save_buffer(
            &apath,
            &rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write all-zones PNG");
        println!(
            "wrote {} — full-map zone terrain ({})",
            apath.display(),
            if outline { "outlined" } else { "smooth/seam-stitched" }
        );
    }

    if let (Some((pid, zid)), Some(zpath)) = (zone_sel, zone_terrain_out) {
        let zr = render_zone(&world, pid, zid, p.seed, &ClassRatios::default());
        image::save_buffer(
            &zpath,
            &zr.rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write zone-terrain PNG");
        println!(
            "wrote {} — zone [{pid},{zid}] class={} base={:.3} relief=[{:.3},{:.3}]",
            zpath.display(),
            zr.class.name(),
            zr.base_elevation,
            zr.min_height,
            zr.max_height
        );
    }

    // **Civ Ship 7d**: civ-layer pipeline — runs only if at least one
    // `--civ-*-out` path was provided.
    let civ_needed = civ_png_out.is_some() || civ_svg_out.is_some() || civ_json_out.is_some();
    if civ_needed {
        use world_gen::civ_adapter::{
            bundle_civ, render_civ_political_png, render_civ_svg,
        };
        let mut bundle = bundle_civ(
            &world,
            &climate,
            civ_ocean_target,
            civ_seed,
            civ_density,
            civ_culture_count,
        );
        // If a real TextProvider is requested, rename via LLM; otherwise
        // synthetic naming already ran inside bundle_civ.
        if !matches!(name_source, NameSource::Synthetic) {
            use std::sync::Arc;
            use world_gen::shape::{AnthropicProvider, OllamaProvider, OpenAIProvider, TextProvider};
            let provider: Arc<dyn TextProvider> = match name_source {
                NameSource::Synthetic => unreachable!(),
                NameSource::Anthropic => {
                    let key = std::env::var("ANTHROPIC_API_KEY")
                        .expect("--name-anthropic requires ANTHROPIC_API_KEY env var");
                    match name_model.as_ref() {
                        Some(m) => Arc::new(AnthropicProvider::with_base_url(
                            key,
                            world_gen::shape::anthropic::DEFAULT_BASE_URL,
                            m,
                        )),
                        None => Arc::new(AnthropicProvider::new(key)),
                    }
                }
                NameSource::OpenAI => {
                    let key = std::env::var("OPENAI_API_KEY")
                        .expect("--name-openai requires OPENAI_API_KEY env var");
                    match name_model.as_ref() {
                        Some(m) => Arc::new(OpenAIProvider::with_base_url(
                            key,
                            world_gen::shape::openai::DEFAULT_BASE_URL,
                            m,
                        )),
                        None => Arc::new(OpenAIProvider::new(key)),
                    }
                }
                NameSource::Ollama => {
                    let model = name_model.clone().unwrap_or_else(|| {
                        world_gen::shape::ollama::DEFAULT_MODEL.to_string()
                    });
                    Arc::new(OllamaProvider::new(model))
                }
                NameSource::LmStudio => {
                    // **Ship 7e**: LM Studio exposes OpenAI-compatible
                    // /v1/chat/completions at http://localhost:1234.
                    // Reuses OpenAIProvider; dummy bearer key (LM Studio
                    // doesn't check auth). **LOW-5 fix (review 2026-05-30)**:
                    // LM Studio requires the exact loaded model name in
                    // the request body — there's no "auto-route to the
                    // single loaded model" behaviour (we burned an iter
                    // on Ship 7e discovering this). Panic with a helpful
                    // probe command instead of silently sending
                    // "local-model" which always rejects with
                    // invalid_request_error.
                    let model = name_model.clone().unwrap_or_else(|| {
                        panic!(
                            "--name-lmstudio requires --name-model <id>. \
                             LM Studio rejects unknown model names with \
                             invalid_request_error — probe the loaded model id with:\n\
                             \n  \
                             curl http://localhost:1234/v1/models | jq -r '.data[].id'\n"
                        )
                    });
                    Arc::new(OpenAIProvider::with_base_url(
                        "lm-studio",
                        world_gen::shape::openai::LMSTUDIO_BASE_URL,
                        model,
                    ))
                }
            };
            // **COSMETIC-2 fix (review 2026-05-30)**: `rename_bundle_in_place`
            // hides the field-shuffle dance (extract → rename → repack
            // → rehash). Err path leaves the synthetic names from
            // `bundle_civ` intact since the MED-1 guard rejects parse
            // failures + under-delivery BEFORE any zip-loops mutate.
            match world_gen::civ_adapter::rename_bundle_in_place(
                &mut bundle,
                provider.as_ref(),
                &civ_archetype,
            ) {
                Ok(()) => {
                    println!("named civ features via {:?}", match name_source {
                        NameSource::Anthropic => "anthropic",
                        NameSource::OpenAI => "openai",
                        NameSource::Ollama => "ollama",
                        NameSource::LmStudio => "lmstudio",
                        NameSource::Synthetic => "synthetic",
                    });
                }
                Err(e) => {
                    eprintln!("LLM naming failed ({e}); keeping synthetic names");
                }
            }
        }

        // Reconstitute Political + Settlements for the renderers.
        let political = world_gen::political::Political {
            province_of: bundle.province_of.clone(),
            provinces: bundle.provinces.clone(),
            states: bundle.states.clone(),
        };

        if let Some(path) = civ_png_out.as_ref() {
            let buf = render_civ_political_png(&world, &political, &bundle.settlements);
            image::save_buffer(
                path,
                &buf,
                world.width,
                world.height,
                image::ExtendedColorType::Rgb8,
            )
            .expect("failed to write civ political PNG");
            println!("wrote {} — civ political map", path.display());
        }
        if let Some(path) = civ_svg_out.as_ref() {
            let svg = render_civ_svg(&world, &political, &bundle.settlements, &bundle.routes);
            std::fs::write(path, svg).expect("failed to write civ SVG");
            println!("wrote {} — civ SVG with labels", path.display());
        }
        if let Some(path) = civ_json_out.as_ref() {
            let json = serde_json::to_string_pretty(&bundle).expect("CivBundle serialize");
            std::fs::write(path, json).expect("failed to write civ JSON");
            println!(
                "wrote {} — CivBundle JSON (content_hash {:?})",
                path.display(),
                &bundle.content_hash[..4]
            );
        }
    }
}
