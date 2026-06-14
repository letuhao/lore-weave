//! `world-gen` CLI — procedural world-map generator (GEO Phases 1–4).
//!
//! ```text
//! world-gen generate --seed 42 --scale continent --coastline island \
//!           --out map.json --relief-png relief.png --png biome.png --style atlas
//! world-gen generate --seed 42 --config creative_seed.json --out map.json
//! # globe view (orthographic), camera looking at lat 0 / lon 90°E:
//! world-gen generate --seed 42 --out map.json --relief-png globe.png \
//!           --projection orthographic --camera 0,1,0
//! world-gen author --brief "a cold mountainous wuxia realm" --out creative_seed.json
//! world-gen name --in map.json --out named.json --archetype wuxia --svg map.svg
//! ```

use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use clap::{Args, Parser, Subcommand, ValueEnum};
use loreweave_llm::{GatewayClient, ModelSource};
use tokio::runtime::{Builder as RuntimeBuilder, Runtime};
use uuid::Uuid;
use world_gen::{
    ClimateZone, CoastlineProfile, CreativeSeed, ErosionStrength, HemisphereOrientation,
    PrevailingWind, Projection, RenderStyle, SettlementDensity, TerrainMode, WorldArchetype,
    WorldMap, WorldScale, generate,
};
use world_gen::shape::GatewayTextProvider;

#[derive(Parser)]
#[command(name = "world-gen", about = "Procedural world-map generator (GEO Phases 1-4)")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
// `GenerateArgs` carries many flags and dwarfs `Author`/`Name`; the enum is
// parsed once at startup, so the size gap is irrelevant and boxing a clap args
// struct would only add noise.
#[allow(clippy::large_enum_variant)]
enum Command {
    /// Generate a world map from a seed + creative direction.
    Generate(GenerateArgs),
    /// Author a CreativeSeed from a prose brief via an LLM.
    Author(AuthorArgs),
    /// Name an existing world map's features via an LLM.
    Name(NameArgs),
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
    /// World archetype (genre). Currently inert — no generation stage reads
    /// it (archetype-driven terrain is deferred to V2).
    #[arg(long, value_enum, default_value_t = ArchetypeArg::HighFantasy)]
    archetype: ArchetypeArg,
    /// Macro-terrain mode. `tectonic` (default) builds a multi-continent
    /// plate-tectonic world; `profile` uses the legacy single-continent
    /// `--coastline` radial mask.
    #[arg(long, value_enum, default_value_t = TerrainModeArg::Tectonic)]
    terrain_mode: TerrainModeArg,
    /// Number of tectonic plates (`tectonic` mode; clamped 3..=24).
    #[arg(long, default_value_t = 8)]
    plate_count: u8,
    /// Fraction of plates carrying continental crust (`tectonic` mode;
    /// clamped 0.1..=0.9). Higher = more land.
    #[arg(long, default_value_t = 0.4)]
    continental_fraction: f32,
    /// How strongly continents spread across latitudes (`tectonic` mode;
    /// clamped 0.0..=1.0). 0 (default) = legacy random placement; 1 = land
    /// covers equator → both poles (tropics + boreal). Opt-in: the full
    /// tropics→tundra gradient also needs the v2 seasonality fix.
    #[arg(long, default_value_t = 0.0)]
    continent_latitude_spread: f32,
    /// Target number of geographic regions (L2) per subcontinent in the
    /// geometric hierarchy (clamped 1..=12).
    #[arg(long, default_value_t = 4)]
    region_subdivision: u8,
    /// Target number of counties per province (political tier; clamped 1..=8).
    #[arg(long, default_value_t = 4)]
    county_subdivision: u8,
    /// Coastline profile (only used in `--terrain-mode profile`).
    #[arg(long, value_enum, default_value_t = CoastlineArg::Coastal)]
    coastline: CoastlineArg,
    /// Hemisphere orientation.
    #[arg(long, value_enum, default_value_t = HemisphereArg::Northern)]
    hemisphere: HemisphereArg,
    /// Prevailing wind direction (the way it blows *from*) — drives the
    /// orographic rain shadow.
    #[arg(long, value_enum, default_value_t = WindArg::West)]
    wind: WindArg,
    /// Hydraulic-erosion strength — how hard water carves valleys.
    #[arg(long, value_enum, default_value_t = ErosionArg::Moderate)]
    erosion: ErosionArg,
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
    /// Cartographic render style for all PNG outputs.
    #[arg(long, value_enum, default_value_t = StyleArg::Realistic)]
    style: StyleArg,
    /// Map projection for all PNG outputs. `equirectangular` is the flat 2:1
    /// world map; `orthographic` is a globe view (a disc; only the camera-
    /// facing hemisphere is visible). SVG export is always equirectangular.
    #[arg(long, value_enum, default_value_t = ProjectionArg::Equirectangular)]
    projection: ProjectionArg,
    /// Orthographic camera direction `x,y,z` (the point on the globe facing
    /// the viewer). Ignored for equirectangular. Default `1,0,0` (lat 0,
    /// lon 0). Need not be normalized.
    #[arg(long)]
    camera: Option<String>,
    /// Optional hypsometric relief-map PNG path (the showcase terrain render).
    #[arg(long)]
    relief_png: Option<PathBuf>,
    /// Optional biome-coloured PNG path.
    #[arg(long)]
    png: Option<PathBuf>,
    /// Optional political-map PNG path.
    #[arg(long)]
    political_png: Option<PathBuf>,
    /// Optional culture-region PNG path.
    #[arg(long)]
    culture_png: Option<PathBuf>,
    /// Optional tectonic-plate PNG path (continental/oceanic tint + boundary
    /// outlines). Empty render in `--terrain-mode profile`.
    #[arg(long)]
    plate_png: Option<PathBuf>,
    /// Optional region-hierarchy PNG path — a 3-tier choropleth: region fill +
    /// continent (near-black) and subcontinent (grey) boundary outlines. A
    /// land-less world renders the biome map.
    #[arg(long)]
    region_png: Option<PathBuf>,
    /// Optional political-tier PNG path — a choropleth: province fill + realm
    /// (near-black) and state (grey) boundary outlines. A land-less world
    /// renders the biome map.
    #[arg(long)]
    realm_png: Option<PathBuf>,
    /// Optional political-map SVG path.
    #[arg(long)]
    svg: Option<PathBuf>,
    /// Optional 3D export — a glTF 2.0 `.glb` displaced globe mesh with an
    /// embedded equirectangular biome texture (open in Blender / Godot / Unity).
    #[arg(long)]
    glb: Option<PathBuf>,
    /// `.glb` mesh grid resolution (longitude segments; latitude = half). Default 512.
    #[arg(long, default_value_t = 512)]
    glb_grid: u32,
    /// `.glb` embedded-texture width (height = half). Default 2048.
    #[arg(long, default_value_t = 2048)]
    glb_texture: u32,
    /// What paints the `.glb` surface: `biome` (climate colour, default),
    /// `region` (continent/subcontinent/region hierarchy), `realm` (political
    /// tiers), or `plate` (tectonic plates). `region`/`realm`/`plate` drape the
    /// structural hierarchy over the same 3D terrain.
    #[arg(long, value_enum, default_value_t = GlbColorArg::Biome)]
    glb_color: GlbColorArg,
    /// `.glb` vertical exaggeration of elevation (planets need it to read). Default 0.06.
    #[arg(long, default_value_t = 0.06)]
    exaggeration: f32,
    /// Optional 16-bit equirectangular heightmap PNG path (terrain-engine input).
    #[arg(long)]
    heightmap_png: Option<PathBuf>,
    /// Heightmap width (height = half). Default 2048.
    #[arg(long, default_value_t = 2048)]
    heightmap_width: u32,
    /// Render detail — **pixels per cell** (linear). The PNG dimensions are
    /// derived from this × the cell count × the projection aspect (2:1 for
    /// equirectangular, 1:1 for orthographic), so a bigger world renders to a
    /// bigger image instead of being squeezed into a fixed square. ~2.5 is a
    /// good default; raise for sharper, lower for faster.
    #[arg(long, default_value_t = 2.5)]
    detail: f32,
    /// Optional explicit render **height** in pixels (width follows the
    /// projection aspect). Overrides `--detail` auto-sizing when set.
    #[arg(long)]
    height: Option<u32>,
}

#[derive(Args)]
struct AuthorArgs {
    /// Prose brief describing the desired world.
    #[arg(long)]
    brief: String,
    /// Output CreativeSeed JSON path.
    #[arg(long)]
    out: PathBuf,
    /// Model registered in provider-registry-service (UUID). The gateway
    /// resolves this to the underlying provider server-side — per
    /// CLAUDE.md provider gateway invariant the CLI does NOT choose a
    /// provider.
    #[arg(long)]
    model_ref: Uuid,
    /// Whether `model_ref` is a platform-shared registration or
    /// per-user (BYOK).
    #[arg(long, value_enum, default_value_t = ModelSourceArg::Platform)]
    model_source: ModelSourceArg,
    /// User the call is billed against. Required by
    /// `/internal/llm/stream`. Generate or supply a real one.
    #[arg(long)]
    user_id: Uuid,
}

#[derive(Args)]
struct NameArgs {
    /// Input WorldMap JSON to name.
    #[arg(long = "in")]
    input: PathBuf,
    /// Output named WorldMap JSON path.
    #[arg(long)]
    out: PathBuf,
    /// World archetype (genre) — steers the naming style.
    #[arg(long, value_enum, default_value_t = ArchetypeArg::HighFantasy)]
    archetype: ArchetypeArg,
    /// Optional labelled political-map SVG output.
    #[arg(long)]
    svg: Option<PathBuf>,
    /// SVG width/height in pixels.
    #[arg(long, default_value_t = 1024)]
    svg_size: u32,
    /// Model registered in provider-registry-service (UUID). See
    /// `AuthorArgs::model_ref` — same semantics.
    #[arg(long)]
    model_ref: Uuid,
    /// Whether `model_ref` is a platform-shared registration or
    /// per-user (BYOK).
    #[arg(long, value_enum, default_value_t = ModelSourceArg::Platform)]
    model_source: ModelSourceArg,
    /// User the call is billed against.
    #[arg(long)]
    user_id: Uuid,
}

#[derive(Clone, Copy, ValueEnum)]
enum ModelSourceArg {
    Platform,
    User,
}

impl From<ModelSourceArg> for ModelSource {
    fn from(s: ModelSourceArg) -> Self {
        match s {
            ModelSourceArg::Platform => ModelSource::PlatformModel,
            ModelSourceArg::User => ModelSource::UserModel,
        }
    }
}

/// Build the shared SDK plumbing every Author / Name subcommand needs.
///
/// Fails fast on missing `LOREWEAVE_INTERNAL_TOKEN` (CLAUDE.md "no
/// hardcoded secrets / services fail to start if missing"). The runtime
/// is `current_thread` + `enable_all` so the SDK's async streaming works
/// inside the sync `TextProvider::complete` block-on path.
fn build_gateway_provider(
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
) -> Result<GatewayTextProvider, String> {
    let client = GatewayClient::from_env().map_err(|e| format!("gateway client: {e}"))?;
    let runtime: Runtime = RuntimeBuilder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|e| format!("tokio runtime: {e}"))?;
    Ok(GatewayTextProvider::new(
        Arc::new(client),
        model_source,
        model_ref,
        user_id,
        Arc::new(runtime),
    ))
}

fn main() -> ExitCode {
    match Cli::parse().command {
        Command::Generate(args) => run_generate(args),
        Command::Author(args) => run_author(args),
        Command::Name(args) => run_name(args),
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
            prevailing_wind: cli.wind.into(),
            erosion: cli.erosion.into(),
            climate_bias: cli.climate_bias.map(Into::into),
            settlement_density: cli.settlement_density.into(),
            culture_count: cli.culture_count,
            terrain_mode: cli.terrain_mode.into(),
            plate_count: cli.plate_count,
            continental_fraction: cli.continental_fraction,
            continent_latitude_spread: cli.continent_latitude_spread,
            region_subdivision: cli.region_subdivision,
            county_subdivision: cli.county_subdivision,
            // Granular tuning + macro knobs default here (set via --config JSON;
            // macro-knob CLI flags land in P8). Defaults = byte-identical.
            ..CreativeSeed::default()
        }
    };

    let map = generate(cli.seed, &cs);

    // Resolve the render projection from the flags.
    let proj = match cli.projection {
        ProjectionArg::Equirectangular => Projection::Equirectangular,
        ProjectionArg::Orthographic => {
            let camera = match parse_camera(cli.camera.as_deref()) {
                Ok(c) => c,
                Err(e) => {
                    eprintln!("error: --camera: {e}");
                    return ExitCode::FAILURE;
                }
            };
            Projection::Orthographic { camera }
        }
    };

    // Render dimensions: explicit height override, else auto-sized from the
    // cell count + projection aspect (so the world isn't crushed into a fixed
    // square). Width follows the projection's aspect either way.
    let (img_w, img_h) = match cli.height {
        Some(h) => (((h as f32) * proj.aspect()).round() as u32, h),
        None => proj.auto_dimensions(map.cell_count(), cli.detail.max(0.5)),
    };

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

    if let Some(png) = &cli.relief_png {
        let img = world_gen::render::relief_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save relief png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.png {
        let img = world_gen::render::biome_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.political_png {
        let img = world_gen::render::political_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save political png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.culture_png {
        let img = world_gen::render::culture_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save culture png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.plate_png {
        let img = world_gen::render::plate_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save plate png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.region_png {
        let img = world_gen::render::region_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save region png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(png) = &cli.realm_png {
        let img = world_gen::render::realm_image(
            &map,
            img_w,
            img_h,
            cli.style.into(),
            proj,
        );
        if let Err(e) = img.save(png) {
            eprintln!("error: save realm png {}: {e}", png.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", png.display());
    }
    if let Some(svg) = &cli.svg {
        let doc = world_gen::render::political_svg(&map, img_h);
        if let Err(e) = std::fs::write(svg, doc) {
            eprintln!("error: write svg {}: {e}", svg.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", svg.display());
    }
    if let Some(path) = &cli.heightmap_png {
        let bytes = world_gen::export::heightmap_png(&map, cli.heightmap_width);
        if let Err(e) = std::fs::write(path, bytes) {
            eprintln!("error: write heightmap {}: {e}", path.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {} (16-bit equirectangular heightmap)", path.display());
    }
    if let Some(path) = &cli.glb {
        let bytes = world_gen::export::glb_globe(
            &map,
            cli.glb_grid,
            (cli.glb_grid / 2).max(2),
            cli.exaggeration,
            cli.glb_texture,
            cli.glb_color.into(),
        );
        if let Err(e) = std::fs::write(path, bytes) {
            eprintln!("error: write glb {}: {e}", path.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {} (glTF 2.0 globe mesh)", path.display());
    }
    ExitCode::SUCCESS
}

fn run_author(cli: AuthorArgs) -> ExitCode {
    let provider = match build_gateway_provider(cli.model_source.into(), cli.model_ref, cli.user_id)
    {
        Ok(p) => p,
        Err(e) => {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    };
    match world_gen::author::request_creative_seed(&cli.brief, &provider) {
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

fn run_name(cli: NameArgs) -> ExitCode {
    let text = match std::fs::read_to_string(&cli.input) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("error: read {}: {e}", cli.input.display());
            return ExitCode::FAILURE;
        }
    };
    let mut map: WorldMap = match serde_json::from_str(&text) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("error: parse map {}: {e}", cli.input.display());
            return ExitCode::FAILURE;
        }
    };
    // A loaded map is verified, not trusted (Phase 4 §2) — names are excluded
    // from the hash, so a previously-named map still verifies here.
    if !map.verify_hash() {
        eprintln!(
            "error: {} failed hash verification — corrupt or hand-edited",
            cli.input.display()
        );
        return ExitCode::FAILURE;
    }
    let provider = match build_gateway_provider(cli.model_source.into(), cli.model_ref, cli.user_id)
    {
        Ok(p) => p,
        Err(e) => {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    };
    if let Err(e) = world_gen::naming::name_world(&mut map, cli.archetype.into(), &provider) {
        eprintln!("error: name: {e}");
        return ExitCode::FAILURE;
    }
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
    println!(
        "wrote {} — named {} settlements, {} realms, {} states, {} provinces, \
         {} counties, {} cultures, {} ranges, {} rivers, {} water bodies",
        cli.out.display(),
        map.settlements.len(),
        map.realms.len(),
        map.states.len(),
        map.provinces.len(),
        map.counties.len(),
        map.culture_regions.len(),
        map.mountain_ranges.len(),
        map.rivers.len(),
        map.water_bodies.len(),
    );
    if let Some(svg) = &cli.svg {
        let doc = world_gen::render::political_svg(&map, cli.svg_size);
        if let Err(e) = std::fs::write(svg, doc) {
            eprintln!("error: write svg {}: {e}", svg.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", svg.display());
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
    Gigaplanet,
}

impl From<ScaleArg> for WorldScale {
    fn from(s: ScaleArg) -> Self {
        match s {
            ScaleArg::Pocket => WorldScale::Pocket,
            ScaleArg::Region => WorldScale::Region,
            ScaleArg::Continent => WorldScale::Continent,
            ScaleArg::SuperContinent => WorldScale::SuperContinent,
            ScaleArg::Megaplanet => WorldScale::Megaplanet,
            ScaleArg::Gigaplanet => WorldScale::Gigaplanet,
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
enum WindArg {
    North,
    NorthEast,
    East,
    SouthEast,
    South,
    SouthWest,
    West,
    NorthWest,
}

impl From<WindArg> for PrevailingWind {
    fn from(w: WindArg) -> Self {
        match w {
            WindArg::North => PrevailingWind::North,
            WindArg::NorthEast => PrevailingWind::NorthEast,
            WindArg::East => PrevailingWind::East,
            WindArg::SouthEast => PrevailingWind::SouthEast,
            WindArg::South => PrevailingWind::South,
            WindArg::SouthWest => PrevailingWind::SouthWest,
            WindArg::West => PrevailingWind::West,
            WindArg::NorthWest => PrevailingWind::NorthWest,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum ErosionArg {
    None,
    Light,
    Moderate,
    Heavy,
}

impl From<ErosionArg> for ErosionStrength {
    fn from(e: ErosionArg) -> Self {
        match e {
            ErosionArg::None => ErosionStrength::None,
            ErosionArg::Light => ErosionStrength::Light,
            ErosionArg::Moderate => ErosionStrength::Moderate,
            ErosionArg::Heavy => ErosionStrength::Heavy,
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

#[derive(Clone, Copy, ValueEnum)]
enum StyleArg {
    Realistic,
    Atlas,
}

impl From<StyleArg> for RenderStyle {
    fn from(s: StyleArg) -> Self {
        match s {
            StyleArg::Realistic => RenderStyle::Realistic,
            StyleArg::Atlas => RenderStyle::Atlas,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum GlbColorArg {
    Biome,
    Region,
    Realm,
    Plate,
}

impl From<GlbColorArg> for world_gen::export::ColorMode {
    fn from(c: GlbColorArg) -> Self {
        use world_gen::export::ColorMode;
        match c {
            GlbColorArg::Biome => ColorMode::Biome,
            GlbColorArg::Region => ColorMode::Region,
            GlbColorArg::Realm => ColorMode::Realm,
            GlbColorArg::Plate => ColorMode::Plate,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum TerrainModeArg {
    Tectonic,
    Profile,
}

impl From<TerrainModeArg> for TerrainMode {
    fn from(m: TerrainModeArg) -> Self {
        match m {
            TerrainModeArg::Tectonic => TerrainMode::Tectonic,
            TerrainModeArg::Profile => TerrainMode::Profile,
        }
    }
}

#[derive(Clone, Copy, ValueEnum)]
enum ProjectionArg {
    Equirectangular,
    Orthographic,
}

/// Parse an Orthographic `--camera x,y,z` triple. Defaults to `[1, 0, 0]`
/// (lat 0, lon 0) when absent. The vector need not be normalized — the
/// projection normalizes it.
fn parse_camera(arg: Option<&str>) -> Result<[f32; 3], String> {
    let Some(s) = arg else {
        return Ok([1.0, 0.0, 0.0]);
    };
    let parts: Vec<&str> = s.split(',').map(str::trim).collect();
    if parts.len() != 3 {
        return Err(format!("expected `x,y,z`, got `{s}`"));
    }
    let mut out = [0.0f32; 3];
    for (i, p) in parts.iter().enumerate() {
        out[i] = p
            .parse::<f32>()
            .map_err(|_| format!("`{p}` is not a number"))?;
    }
    if out.iter().all(|c| *c == 0.0) {
        return Err("camera direction must be non-zero".to_string());
    }
    Ok(out)
}
