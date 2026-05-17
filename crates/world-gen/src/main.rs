//! `world-gen` CLI — generate a world map from a seed + creative config.
//!
//! ```text
//! world-gen --seed 42 --scale continent --coastline island \
//!           --out map.json --png map.png
//! ```

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, ValueEnum};
use world_gen::{
    ClimateZone, CoastlineProfile, CreativeSeed, HemisphereOrientation, WorldArchetype, WorldScale,
    generate,
};

#[derive(Parser)]
#[command(name = "world-gen", about = "Procedural world-map generator (GEO Phases 1-2)")]
struct Cli {
    /// 64-bit generation seed.
    #[arg(long)]
    seed: u64,
    /// World scale (sets the mesh size).
    #[arg(long, value_enum, default_value_t = ScaleArg::Continent)]
    scale: ScaleArg,
    /// World archetype (genre).
    #[arg(long, value_enum, default_value_t = ArchetypeArg::HighFantasy)]
    archetype: ArchetypeArg,
    /// Coastline profile (shapes the heightmap).
    #[arg(long, value_enum, default_value_t = CoastlineArg::Coastal)]
    coastline: CoastlineArg,
    /// Hemisphere orientation (drives latitude → climate).
    #[arg(long, value_enum, default_value_t = HemisphereArg::Northern)]
    hemisphere: HemisphereArg,
    /// Optional climate-zone bias.
    #[arg(long, value_enum)]
    climate_bias: Option<ClimateBiasArg>,
    /// Output JSON path.
    #[arg(long)]
    out: PathBuf,
    /// Optional biome-coloured PNG path.
    #[arg(long)]
    png: Option<PathBuf>,
    /// PNG width/height in pixels.
    #[arg(long, default_value_t = 1024)]
    png_size: u32,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let cs = CreativeSeed {
        world_scale: cli.scale.into(),
        world_archetype: cli.archetype.into(),
        coastline_profile: cli.coastline.into(),
        hemisphere_orientation: cli.hemisphere.into(),
        climate_bias: cli.climate_bias.map(Into::into),
    };
    let map = generate(cli.seed, &cs);

    let json = match serde_json::to_string_pretty(&map) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("error: serialize map: {e}");
            return ExitCode::FAILURE;
        }
    };
    if let Err(e) = std::fs::write(&cli.out, json) {
        eprintln!("error: write {}: {e}", cli.out.display());
        return ExitCode::FAILURE;
    }
    let hash_hex: String = map
        .content_hash
        .iter()
        .take(8)
        .map(|b| format!("{b:02x}"))
        .collect();
    println!(
        "wrote {} — {} cells, sea_level {}, hash {hash_hex}…",
        cli.out.display(),
        map.cell_count(),
        map.sea_level,
    );

    if let Some(png) = &cli.png {
        let img = world_gen::render::biome_image(&map, cli.png_size, cli.png_size);
        if let Err(e) = img.save(png) {
            eprintln!("error: save png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    ExitCode::SUCCESS
}

// --- CLI-local mirror enums (keep the library free of a clap dependency) ---

#[derive(Clone, Copy, ValueEnum)]
enum ScaleArg {
    Pocket,
    Region,
    Continent,
    SuperContinent,
    Megaplanet,
}

impl From<ScaleArg> for WorldScale {
    fn from(s: ScaleArg) -> Self {
        match s {
            ScaleArg::Pocket => WorldScale::Pocket,
            ScaleArg::Region => WorldScale::Region,
            ScaleArg::Continent => WorldScale::Continent,
            ScaleArg::SuperContinent => WorldScale::SuperContinent,
            ScaleArg::Megaplanet => WorldScale::Megaplanet,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum ArchetypeArg {
    Wuxia,
    HighFantasy,
    LowFantasy,
    Cyberpunk,
    SteamPunk,
    Postapocalyptic,
    ScienceFiction,
    Historical,
    Mythological,
    Romance,
    Mystery,
    Custom,
}

impl From<ArchetypeArg> for WorldArchetype {
    fn from(a: ArchetypeArg) -> Self {
        match a {
            ArchetypeArg::Wuxia => WorldArchetype::Wuxia,
            ArchetypeArg::HighFantasy => WorldArchetype::HighFantasy,
            ArchetypeArg::LowFantasy => WorldArchetype::LowFantasy,
            ArchetypeArg::Cyberpunk => WorldArchetype::Cyberpunk,
            ArchetypeArg::SteamPunk => WorldArchetype::SteamPunk,
            ArchetypeArg::Postapocalyptic => WorldArchetype::Postapocalyptic,
            ArchetypeArg::ScienceFiction => WorldArchetype::ScienceFiction,
            ArchetypeArg::Historical => WorldArchetype::Historical,
            ArchetypeArg::Mythological => WorldArchetype::Mythological,
            ArchetypeArg::Romance => WorldArchetype::Romance,
            ArchetypeArg::Mystery => WorldArchetype::Mystery,
            ArchetypeArg::Custom => WorldArchetype::Custom,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum CoastlineArg {
    Island,
    Peninsula,
    Coastal,
    Inland,
    Archipelago,
}

impl From<CoastlineArg> for CoastlineProfile {
    fn from(c: CoastlineArg) -> Self {
        match c {
            CoastlineArg::Island => CoastlineProfile::Island,
            CoastlineArg::Peninsula => CoastlineProfile::Peninsula,
            CoastlineArg::Coastal => CoastlineProfile::Coastal,
            CoastlineArg::Inland => CoastlineProfile::Inland,
            CoastlineArg::Archipelago => CoastlineProfile::Archipelago,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum HemisphereArg {
    Northern,
    Southern,
    Equatorial,
}

impl From<HemisphereArg> for HemisphereOrientation {
    fn from(h: HemisphereArg) -> Self {
        match h {
            HemisphereArg::Northern => HemisphereOrientation::Northern,
            HemisphereArg::Southern => HemisphereOrientation::Southern,
            HemisphereArg::Equatorial => HemisphereOrientation::Equatorial,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum ClimateBiasArg {
    Polar,
    Boreal,
    Temperate,
    Mediterranean,
    Subtropical,
    Tropical,
    Arid,
    Highland,
}

impl From<ClimateBiasArg> for ClimateZone {
    fn from(c: ClimateBiasArg) -> Self {
        match c {
            ClimateBiasArg::Polar => ClimateZone::Polar,
            ClimateBiasArg::Boreal => ClimateZone::Boreal,
            ClimateBiasArg::Temperate => ClimateZone::Temperate,
            ClimateBiasArg::Mediterranean => ClimateZone::Mediterranean,
            ClimateBiasArg::Subtropical => ClimateZone::Subtropical,
            ClimateBiasArg::Tropical => ClimateZone::Tropical,
            ClimateBiasArg::Arid => ClimateZone::Arid,
            ClimateBiasArg::Highland => ClimateZone::Highland,
        }
    }
}
