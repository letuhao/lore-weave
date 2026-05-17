//! `world-gen` CLI — procedural world-map generator (GEO Phases 1–4).
//!
//! ```text
//! world-gen generate --seed 42 --scale continent --coastline island \
//!           --out map.json --png biome.png --political-png pol.png --svg map.svg
//! world-gen generate --seed 42 --config creative_seed.json --out map.json
//! world-gen author --brief "a cold mountainous wuxia realm" --out creative_seed.json
//! ```

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Args, Parser, Subcommand, ValueEnum};
use world_gen::{
    ClimateZone, CoastlineProfile, CreativeSeed, HemisphereOrientation, SettlementDensity,
    WorldArchetype, WorldScale, generate,
};

#[derive(Parser)]
#[command(name = "world-gen", about = "Procedural world-map generator (GEO Phases 1-4)")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Generate a world map from a seed + creative direction.
    Generate(GenerateArgs),
    /// Author a CreativeSeed from a prose brief via an LLM.
    Author(AuthorArgs),
}

#[derive(Args)]
struct GenerateArgs {
    /// 64-bit generation seed.
    #[arg(long)]
    seed: u64,
    /// Load the CreativeSeed from a JSON file (overrides the creative flags).
    #[arg(long)]
    config: Option<PathBuf>,
    /// World scale (sets the mesh size).
    #[arg(long, value_enum, default_value_t = ScaleArg::Continent)]
    scale: ScaleArg,
    /// World archetype (genre).
    #[arg(long, value_enum, default_value_t = ArchetypeArg::HighFantasy)]
    archetype: ArchetypeArg,
    /// Coastline profile.
    #[arg(long, value_enum, default_value_t = CoastlineArg::Coastal)]
    coastline: CoastlineArg,
    /// Hemisphere orientation.
    #[arg(long, value_enum, default_value_t = HemisphereArg::Northern)]
    hemisphere: HemisphereArg,
    /// Optional climate-zone bias.
    #[arg(long, value_enum)]
    climate_bias: Option<ClimateBiasArg>,
    /// Settlement placement density.
    #[arg(long, value_enum, default_value_t = DensityArg::Medium)]
    settlement_density: DensityArg,
    /// Number of culture regions (clamped 1..=16).
    #[arg(long, default_value_t = 5)]
    culture_count: u8,
    /// Output JSON path.
    #[arg(long)]
    out: PathBuf,
    /// Optional biome-coloured PNG path.
    #[arg(long)]
    png: Option<PathBuf>,
    /// Optional political-map PNG path.
    #[arg(long)]
    political_png: Option<PathBuf>,
    /// Optional culture-region PNG path.
    #[arg(long)]
    culture_png: Option<PathBuf>,
    /// Optional political-map SVG path.
    #[arg(long)]
    svg: Option<PathBuf>,
    /// PNG/SVG width/height in pixels.
    #[arg(long, default_value_t = 1024)]
    png_size: u32,
}

#[derive(Args)]
struct AuthorArgs {
    /// Prose brief describing the desired world.
    #[arg(long)]
    brief: String,
    /// Output CreativeSeed JSON path.
    #[arg(long)]
    out: PathBuf,
    /// OpenAI-compatible LLM API base URL.
    #[arg(long, default_value = "http://localhost:1234/v1")]
    llm_url: String,
    /// LLM model id.
    #[arg(long, default_value = "ibm/granite-4-h-tiny")]
    llm_model: String,
}

fn main() -> ExitCode {
    match Cli::parse().command {
        Command::Generate(args) => run_generate(args),
        Command::Author(args) => run_author(args),
    }
}

fn run_generate(cli: GenerateArgs) -> ExitCode {
    // CreativeSeed: from --config JSON if given, else from the creative flags.
    let cs = if let Some(config) = &cli.config {
        match std::fs::read_to_string(config) {
            Ok(text) => match serde_json::from_str::<CreativeSeed>(&text) {
                Ok(cs) => cs,
                Err(e) => {
                    eprintln!("error: parse config {}: {e}", config.display());
                    return ExitCode::FAILURE;
                }
            },
            Err(e) => {
                eprintln!("error: read config {}: {e}", config.display());
                return ExitCode::FAILURE;
            }
        }
    } else {
        CreativeSeed {
            world_scale: cli.scale.into(),
            world_archetype: cli.archetype.into(),
            coastline_profile: cli.coastline.into(),
            hemisphere_orientation: cli.hemisphere.into(),
            climate_bias: cli.climate_bias.map(Into::into),
            settlement_density: cli.settlement_density.into(),
            culture_count: cli.culture_count,
        }
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
        "wrote {} — {} cells, {} provinces, {} states, {} settlements, {} routes, hash {hash_hex}…",
        cli.out.display(),
        map.cell_count(),
        map.provinces.len(),
        map.states.len(),
        map.settlements.len(),
        map.routes.len(),
    );

    if let Some(png) = &cli.png {
        let img = world_gen::render::biome_image(&map, cli.png_size, cli.png_size);
        if let Err(e) = img.save(png) {
            eprintln!("error: save png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.political_png {
        let img = world_gen::render::political_image(&map, cli.png_size, cli.png_size);
        if let Err(e) = img.save(png) {
            eprintln!("error: save political png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.culture_png {
        let img = world_gen::render::culture_image(&map, cli.png_size, cli.png_size);
        if let Err(e) = img.save(png) {
            eprintln!("error: save culture png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(svg) = &cli.svg {
        let doc = world_gen::render::political_svg(&map, cli.png_size);
        if let Err(e) = std::fs::write(svg, doc) {
            eprintln!("error: write svg {}: {e}", svg.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", svg.display());
    }
    ExitCode::SUCCESS
}

fn run_author(cli: AuthorArgs) -> ExitCode {
    match world_gen::author::request_creative_seed(&cli.brief, &cli.llm_url, &cli.llm_model) {
        Ok(cs) => match serde_json::to_string_pretty(&cs) {
            Ok(json) => {
                if let Err(e) = std::fs::write(&cli.out, json) {
                    eprintln!("error: write {}: {e}", cli.out.display());
                    return ExitCode::FAILURE;
                }
                println!("wrote {} — {cs:?}", cli.out.display());
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("error: serialize CreativeSeed: {e}");
                ExitCode::FAILURE
            }
        },
        Err(e) => {
            eprintln!("error: author: {e}");
            ExitCode::FAILURE
        }
    }
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

#[derive(Clone, Copy, ValueEnum)]
enum DensityArg {
    Sparse,
    Medium,
    Dense,
}

impl From<DensityArg> for SettlementDensity {
    fn from(d: DensityArg) -> Self {
        match d {
            DensityArg::Sparse => SettlementDensity::Sparse,
            DensityArg::Medium => SettlementDensity::Medium,
            DensityArg::Dense => SettlementDensity::Dense,
        }
    }
}
