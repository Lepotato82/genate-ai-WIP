# Decoration Assets — Attribution & License

All PNGs under `assets/decorations/` are used by the compositor's decorative
asset layer (`agents/asset_layer.py`, `agents/compositor.py::_stamp_decoration`).
The layer is gated by `COMPOSITOR_DECORATIONS_ENABLED` in `config/settings.py`.

## consumer-friendly/

Starter pack: six procedurally-generated botanical decorations.

| File | Source | License |
|---|---|---|
| `botanical_sprig_01.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |
| `citrus_cluster_02.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |
| `leaf_arc_03.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |
| `herb_sprig_04.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |
| `floral_dots_05.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |
| `mixed_bunch_06.png` | Procedurally generated via `scripts/generate_decorations.py` | MIT (project) |

The starter pack uses Pillow primitives (ellipses, rotated leaf shapes,
Gaussian softening) to draw natural botanical silhouettes. Output is
deterministic — rerunning the script produces byte-identical PNGs.

### Regenerating

```bash
python scripts/generate_decorations.py
```

### Replacing with curated artwork

You can drop in any PNG files with transparent backgrounds into
`assets/decorations/consumer-friendly/` — the asset layer is file-agnostic.
Preferred properties:

- Transparent background
- ~800×800 (compositor downscales to fit each slide; larger is fine)
- Single subject, centered or anchored to one side
- Natural botanical/wellness vibe for consumer-friendly

Recommended free sources with compatible licenses:

- **unDraw** (https://undraw.co) — MIT, re-colorable SVG
- **OpenMoji** (https://openmoji.org) — CC-BY-SA 4.0 (requires attribution)
- **OpenClipart** (https://openclipart.org) — CC0 (public domain)
- **Vecteezy** free tier — check individual license (some require attribution)

When you add curated assets, add a row above with source URL and license.
Any CC-BY-SA assets must credit the original author here.

## Other categories

Not yet seeded. The asset layer returns `[None]` per slide for any category
with no files, so the compositor simply skips the decoration stamp for
brands that fall into those categories. Add curated assets under:

- `assets/decorations/developer-tool/`
- `assets/decorations/minimal-saas/`
- `assets/decorations/bold-enterprise/`
- `assets/decorations/data-dense/`
