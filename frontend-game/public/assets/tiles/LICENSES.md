# Asset license audit — tiles

Per spec §13 and /review-impl MED-9 (per-pack license audit). Every art
pack vendored under `public/assets/tiles/` must be listed here with its
exact license, source URL, and any attribution requirements.

| Pack | Source | License | Attribution required? | Notes |
|---|---|---|---|---|
| **Kenney Isometric Tiles Landscape** | https://kenney.nl/assets/isometric-tiles-landscape | **CC0 1.0 Universal (Public Domain)** | No (CC0 is dedication to public domain) | We credit anyway under "Acknowledgements" in PACKAGES.md. Tile dims 128×128 PNG canvas; iso diamond inside is 128×64 — matches spec §1 #10. |

## License rule

This file MUST be updated **in the same commit** that adds any new pack
under `public/assets/tiles/`. CI may later block PRs that add PNG/JPG
to assets/ without a corresponding LICENSES.md entry.

## CC0 declaration verification

Kenney's CC0 license is documented at https://creativecommons.org/publicdomain/zero/1.0/.
Each Kenney pack ships with its own `License.txt` confirming CC0. We do
NOT remove or modify those files when unzipping — they stay in place
inside the pack folder as cryptographic evidence of the grant.

## Future packs to add

When V0 demo expands beyond a single grass tile, candidates from the
same Kenney series (all CC0):
- `kenney_isometric-roads` — paths for connecting villages
- `kenney_isometric-roads-water` — bridges + water transitions
- `kenney_isometric-tiles-city` — village/town buildings
- `kenney_isometric-tiles-buildings` — single buildings

NPC + Player character sprites likely come from a separate pack — Kenney
"Toon Characters 1" (CC0) or similar. To be researched in Session E+.
