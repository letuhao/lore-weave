# Deep-research findings — geological elevation formation (for the elevation redesign)

> Source: deep-research workflow (105 agents, 23 sources fetched, 94 claims → 25 verified, 9 synthesized). 2026-05-31.

## Synthesis

Earth's elevation is fundamentally bimodal — two distinct modes (continental platform a few hundred meters above sea level, abyssal plains ~4,300 m below) — because oceanic and continental crust differ in density AND thickness, so isostasy floats them at two different heights. A geologically-realistic procedural heightmap should therefore be built as a sequence: (1) set a two-mode isostatic base from per-cell crust type/thickness, (2) drive relief at plate boundaries by interaction type (subduction → arc+trench, collision → high mountains with no trench, divergence → ridge/rift), (3) age the oceanic crust so depth grows as ~sqrt(age) and flattens for old crust, then (4) couple uplift with stream-power fluvial erosion plus nonlinear hillslope diffusion until the landscape relaxes toward an uplift/erosion steady state. The canonical established algorithms for exactly this pipeline are Cortial et al. 2019 "Procedural Tectonic Planets" (phenomenological tectonics on a spherical Voronoi/Delaunay mesh + relief amplification) and Cordonnier et al. 2016 (tectonic uplift coupled to fluvial stream-power erosion, dh/dt = u − k·A^m·S^n), both of which supply concrete parameter magnitudes. Caveat: the verified claims strongly cover the tectonic-uplift→erosion machinery and the bimodality target, but supply fewer hard numeric magnitudes for the explicit isostatic-equilibrium equations and per-boundary trench/arc relief decay, and one attempt to pin fixed elevation band values from Cortial was refuted — those bands must be calibrated against the hypsometric target rather than read off a paper.

## Verified findings

### 1. [HIGH] Earth's elevation distribution is bimodal — two modes (continental land ~several hundred m above sea level; oceanic abyssal plains ~4,300 m below) — and this bimodality is the realism TARGET a heightmap must reproduce. It exists because oceanic vs continental crust are fundamentally physically different (density + thickness), confirmed by extensive research.

**Evidence:** NOAA/NCEI ETOPO1 hypsographic source states verbatim two primary groupings — continents several hundred m above SL, abyssal plains ~4,300 m below SL — and that ocean-floor crust 'is fundamentally different from the continents, a distinction confirmed by countless research studies.' Corroborated by Whitehead 2009 JGR (doi:10.1029/2008JB006176) and standard hypsometry references. Mode magnitudes vary slightly across sources (continental mode ~+100 m, oceanic mode ~-4,700 m elsewhere) but fall within the cited spread.

**Sources:** https://www.ncei.noaa.gov/sites/default/files/2023-01/Hypsographic%20Curve%20of%20Earth%E2%80%99s%20Surface%20from%20ETOPO1.pdf

### 2. [HIGH] Continental crust thickness spans ~10 km (thin, rifted margins, just thicker than oceanic crust) to >80 km at collisional convergent margins (Himalaya-Tibet). This is the thickness range an isostasy-driven generator must model, because isostatic surface height depends on crustal thickness, not just density.

**Evidence:** Scientific Reports 2017 (PMC5539297): continental crust 'ranges from just a few kilometers thicker than oceanic crust (~6–10 km) to over 80 km at some convergent margins, such as in Himalaya-Tibet.' Corroborated by Nature Communications s41467-021-21420-z ('80 km thick Tibetan crust'). Implication for generator: thickened crust at collision boundaries floats higher isostatically — the mechanism behind high fold mountains with no trench.

**Sources:** https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5539297/

### 3. [HIGH] Oceanic bathymetry follows an age–depth law: young ridge crust is shallow and depth increases as ~sqrt(age). The half-space cooling model gives d ∝ sqrt(age), but for OLD crust depth flattens rather than continuing to deepen — so a procedural bathymetry step must use a flattening plate-cooling model (GDH1), not pure half-space cooling, for old seafloor.

**Evidence:** Stein & Stein 1992 (Nature 359:123, GDH1 = Global Depth and Heat flow): joint fit of bathymetry + heat flow yields hotter/thinner lithosphere than Parsons-Sclater PSM (GDH1: 95 km plate, 1450°C basal T vs PSM 125 km, 1350°C), and fits old lithosphere 'previously treated as anomalous' better — depth flattens to ~6,400 m. GDH1 subsidence law: d = 2600 + 365·sqrt(t) for t<20 Myr. Korenaga & Korenaga 2008 (EPSL 268:41): 'normal' seafloor subsides at ~320 m·Ma^-1/2 (~10% below the conventional ~350 of Parsons-Sclater 1977), and argues sqrt-age half-space cooling is consistent once viscoelastic effective thermal expansivity is accounted for (this reinterpretation of old-crust flattening is debated, 2-1 vote on claim [6]).

**Sources:** https://www.nature.com/articles/359123a0; https://www.korenaga.yale.edu/_files/ugd/...korenaga08b.pdf

### 4. [HIGH] The canonical erosion engine is the stream-power incision law (SPIM): E = K·A^m·S^n, where E is vertical incision rate, K erodibility, A upstream drainage area, S channel gradient, m and n exponents. It is coupled to a detachment-limited mass balance dh/dt = U − K·A^m·(dh/dx)^n where U is rock uplift / baselevel-lowering rate.

**Evidence:** Lague 2014 ESPL (verbatim eq. extracted from PDF): I = K·A^m·S^n and dh/dt = U − I = U − K·A^m·(dh/dx)^n, 'detachment-limited,' U = baselevel lowering / rock uplift. Adams/Pelletier/McGuire 2017 esurf abstract gives identical form and variable definitions. Whipple & Tucker 1999 JGR is the foundational primary derivation. SPIM is 'the most widely used model for bedrock channel incision.'

**Sources:** https://wpg.forestry.oregonstate.edu/sites/default/files/seminars/2014_Lague_ESPL.pdf; https://esurf.copernicus.org/articles/5/807/2017/; https://sseh.uchicago.edu/doc/Whipple_and_Tucker_1999.pdf

### 5. [HIGH] Standard SPIM exponents: m/n ≈ 0.5 (the channel concavity index θ = m/n), with the energetic derivation giving m = 0.5, n = 1 — the most common modeling choice. m,n depend on rock strength, climate, and river-network topology; the model PREDICTS 0.35 < m/n < 0.6 for typical hydraulic-geometry exponents.

**Evidence:** Whipple & Tucker 1999: m/n predicted in narrow range near 0.5 (0.35–0.6) for typical exponents. esurf 2017: 'The most common choice of exponents satisfies m/n = 0.5.' Lague 2014: energetic considerations yield m=0.5, n=1; θ = m/n; any n≈2m yields a valid SPIM. Cordonnier 2016: 'As in most geomorphological studies, we use n = 1 and m = 0.5.' NUANCE: Lague's headline finding is that steady-state slope–area concavity does NOT uniquely constrain n; sensitivity arguments suggest n~2, m~1 for many real cases — n=1 is the conventional modeling choice, not settled physics ([12] 2-1, [20] 3-0).

**Sources:** https://sseh.uchicago.edu/doc/Whipple_and_Tucker_1999.pdf; https://wpg.forestry.oregonstate.edu/sites/default/files/seminars/2014_Lague_ESPL.pdf; https://esurf.copernicus.org/articles/5/807/2017/; https://www.cs.purdue.edu/cgvlab/www/resources/papers/Cordonnier-Computer_Graphics_Forum-2016-Large_Scale_Terrain_Generation_from_Tectonic_Uplift_and_Fluvial_.pdf

### 6. [HIGH] At steady state local erosion everywhere balances rock uplift (dz/dt = 0). This gives equilibrium concave river/mountain profiles: slope S = (U/(K·A^m))^(1/n), i.e. S ∝ A^(-m/n) (Flint's law), and equilibrium gradient/relief scales with the uplift-erosion number raised to 1/n. Sensitivity to uplift/lithology/climate is dictated by n: n=1 → linear, n>1 → weak, n<1 → very sensitive.

**Evidence:** Whipple & Tucker 1999: steepness depends on uplift-erosion number raised to 1/n; n=2/3 very sensitive, n=1 linear, n>1 weakly dependent; at steady state dz/dt=0 and local erosion balances rock uplift everywhere, defining equilibrium profiles and range envelopes. Cordonnier 2016: setting dh=0 in u − k·A^m·s^n gives s ∝ A^(-m/n), producing concave equilibrium profiles. This balance is what shapes realistic mountain relief and drainage.

**Sources:** https://sseh.uchicago.edu/doc/Whipple_and_Tucker_1999.pdf; https://www.cs.purdue.edu/cgvlab/www/resources/papers/Cordonnier-Computer_Graphics_Forum-2016-Large_Scale_Terrain_Generation_from_Tectonic_Uplift_and_Fluvial_.pdf

### 7. [HIGH] Hillslope (short-wavelength) relief is shaped by slope-dependent diffusive soil transport, which COMPLEMENTS channel stream-power incision — both are needed for realistic terrain. The transport is nonlinear: flux ≈ linear diffusion (q ∝ S) at gentle slopes but diverges toward infinity as slope approaches a critical gradient S_c. Roering et al. law: q = K·S / (1 − (S/S_c)^2).

**Evidence:** Roering, Kirchner & Dietrich 1999 (Water Resources Research 35(3):853): nonlinear hillslope transport q = K·S/(1−(S/S_c)^2) — linear diffusion at low gradient, flux→∞ as S→S_c. Steep soil-mantled hillslopes evolve by slope-dependent downslope soil movement; this is the dominant short-wavelength relief-smoothing process complementing fluvial incision (the hillslope-diffusion + stream-power pairing used in Landlab/FastScape/CHILD). Implication: linear diffusion underpredicts transport near failure-angle slopes.

**Sources:** https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/1998wr900090

### 8. [HIGH] The established end-to-end algorithm is Cortial et al. 2019 'Procedural Tectonic Planets' — a phenomenological (non-physically-simulated) heuristic on a spherical Voronoi/Delaunay mesh that drives elevation from FOUR plate-interaction types: subduction + continental collision (convergent), oceanic crust generation (divergent), and rifting. It deforms continental and oceanic crust from plate movement to produce continents, oceanic ridges, mountain ranges, and island arcs, then amplifies the coarse crust into detailed relief. This validates the thesis that boundary type — not generic noise — should drive elevation.

**Evidence:** Cortial et al. 2019 (Computer Graphics Forum, Eurographics, doi:10.1111/cgf.13614): 'Instead of relying on computationally demanding physically-based simulations, we capture the fundamental phenomena into a procedural method.' Models four interaction types at convergent/divergent boundaries + rifting; generates 'continents, oceanic ridges, large scale mountain ranges or island arcs' from plate movement, then 'amplify[s] the large-scale planet model with either procedurally-defined or real-world elevation data to synthesize coherent detailed reliefs.' Noise is used only for detail amplification on top of tectonics. REFUTED sub-claim: this paper does NOT supply fixed reusable elevation-band reference values (sea level=0, ridge=-1km, abyss=-6km, trench=-10km, continent=+10km) — that claim was 0-3; bands must be calibrated to the hypsometric target instead.

**Sources:** https://onlinelibrary.wiley.com/doi/10.1111/cgf.13614; https://hal.science/hal-02136820v1/file/2019-Procedural-Tectonic-Planets.pdf

### 9. [HIGH] The recommended uplift→erosion coupling pipeline (Cortial 2019; Cordonnier 2016) generates a volumetric uplift map from boundary tectonics, then JOINTLY simulates erosion with uplift movement. The concrete coupling equation is dh/dt = u(p) − k·A(p)^m·s(p)^n. Concrete tuned magnitudes from Cordonnier 2016: max tectonic uplift U = 5.0×10^-4 m/yr (avg orogenic uplift), erosion rate k = 5.61×10^-7 yr^-1 (mountains culminate ~2000 m), geological time step Δt = 2.5×10^5 yr, with max height following the linear rule h_max(km) = 2.244·u/k.

**Evidence:** Cortial 2019: 'The model generates a volumetric uplift map representing the growth rate of subsurface layers, and erosion and uplift movement are jointly simulated to generate terrain' (concurrent coupling, not strictly sequential). Cordonnier 2016 (PDF text-extracted, verbatim): U = 5.0×10^-4 m/yr 'average uplift among earth mountains'; k = 5.61×10^-7 yr^-1 'for mountains to culminate at about 2000 m'; Δt = 2.5×10^5 yr 'to ensure fast convergence while avoiding high unnatural cliffs'; h_max = 2.244·u/k. CAVEAT: these are tool parameters tuned for visual plausibility (the k/u ratio is acknowledged as not well-constrained geologically), not independently-validated geophysical constants.

**Sources:** https://hal.science/hal-02136820v1/file/2019-Procedural-Tectonic-Planets.pdf; https://www.cs.purdue.edu/cgvlab/www/resources/papers/Cordonnier-Computer_Graphics_Forum-2016-Large_Scale_Terrain_Generation_from_Tectonic_Uplift_and_Fluvial_.pdf
