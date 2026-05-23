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
use world_gen::flat_climate::{HemisphereLayout, WorldClimateParams};
use world_gen::zonegen::{
    render_all_zones, render_all_zones_biome, render_all_zones_eroded, render_zone, zone_height,
    ClassRatios, TerrainClass,
};

fn main() {
    let mut p = FlatParams::default();
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
    let mut climate = WorldClimateParams::default();
    // Whether the user overrode continentality_reach explicitly (skip auto-scale).
    let mut reach_explicit = false;

    // Minimal hand-rolled arg parsing (`--flag value`), to keep the sketch
    // dependency-free of the main CLI.
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        let flag = args[i].as_str();
        let val = args.get(i + 1).cloned();
        let need = || val.clone().unwrap_or_else(|| panic!("{flag} needs a value"));
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
            other => panic!("unknown flag: {other}"),
        }
        i += 2;
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
        let total: usize = world.plates.iter().map(|p| p.zone_sites.len()).sum();
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
}
