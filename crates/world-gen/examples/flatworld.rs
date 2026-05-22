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
use world_gen::zonegen::{render_all_zones, render_zone, ClassRatios};

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

    if let Some(apath) = all_zones_out {
        let rgb = render_all_zones(&world, p.seed, &ClassRatios::default());
        image::save_buffer(
            &apath,
            &rgb,
            world.width,
            world.height,
            image::ExtendedColorType::Rgb8,
        )
        .expect("failed to write all-zones PNG");
        println!("wrote {} — full-map zone terrain", apath.display());
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
