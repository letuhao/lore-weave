//! Criterion benchmark — `cargo bench`.
//!
//! Times the two heavy paths of the generator: `generate()` across every
//! `WorldScale` (Pocket … Gigaplanet), and `relief_image` rendering at the
//! largest scale. `Gigaplanet` is ~501k cells, so a single iteration is
//! seconds of work — the groups use criterion's minimum `sample_size(10)`;
//! the small scales tolerate that fine.

use std::hint::black_box;

use criterion::{Criterion, criterion_group, criterion_main};
use world_gen::render::relief_image;
use world_gen::{CreativeSeed, RenderStyle, WorldScale, generate};

const SEED: u64 = 20_260_518;

/// `generate(seed, &cs)` for each scale, `cs` = default varied only by scale.
fn bench_generate(c: &mut Criterion) {
    let scales = [
        ("pocket", WorldScale::Pocket),
        ("region", WorldScale::Region),
        ("continent", WorldScale::Continent),
        ("supercontinent", WorldScale::SuperContinent),
        ("megaplanet", WorldScale::Megaplanet),
        ("gigaplanet", WorldScale::Gigaplanet),
    ];
    let mut group = c.benchmark_group("generate");
    group.sample_size(10);
    for (name, scale) in scales {
        let cs = CreativeSeed {
            world_scale: scale,
            ..CreativeSeed::default()
        };
        group.bench_function(name, |b| {
            b.iter(|| generate(black_box(SEED), black_box(&cs)));
        });
    }
    group.finish();
}

/// The other heavy path — rendering the largest map (relief + supersampling).
fn bench_render(c: &mut Criterion) {
    let cs = CreativeSeed {
        world_scale: WorldScale::Gigaplanet,
        ..CreativeSeed::default()
    };
    let map = generate(SEED, &cs);
    let mut group = c.benchmark_group("render");
    group.sample_size(10);
    group.bench_function("relief_gigaplanet_2048", |b| {
        b.iter(|| relief_image(black_box(&map), 2048, 2048, RenderStyle::Realistic));
    });
    group.finish();
}

criterion_group!(benches, bench_generate, bench_render);
criterion_main!(benches);
