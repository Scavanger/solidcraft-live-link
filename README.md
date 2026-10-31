# SolidCraft Live Link for Blender

[![CI](https://github.com/Scavanger/solidcraft-live-link/actions/workflows/ci.yml/badge.svg)](https://github.com/Scavanger/solidcraft-live-link/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Scavanger/solidcraft-live-link)](https://github.com/Scavanger/solidcraft-live-link/releases/latest)

Follow the design open in [SolidCraft](https://github.com/tangency-labs/solidcraft) live in
Blender, as meshes ready to texture, render or prepare for a game:

- **Live**: every change in SolidCraft (an edit, a parameter, undo, a body shown or hidden) arrives
  within a moment; only the bodies that changed are sent again.
- **Clean topology**: welded, closed meshes; one n-gon per flat face, quads on cylinders, cones,
  fillets and revolved faces, triangles only where a surface needs them (a sphere's poles).
- **CAD faces kept**: every polygon carries its B-rep face (`sc_face`), every face boundary is a
  UV seam, creases are marked sharp, tangent joins are not, and corners take the true surface
  normals as custom normals, so a coarse mesh still shades like the CAD surface.
- **Refacet**: ask for coarser or finer meshes, for the scene or for the selected bodies.
- **Assemblies**: one collection per component; a part placed several times shares one mesh.

Blender only reads: the design is never changed from here.

## Install

Requires Blender 4.2 or later and a SolidCraft with the live link (`live.meshes`).

1. Download `solidcraft_link-<version>.zip` from the [latest release](https://github.com/Scavanger/solidcraft-live-link/releases/latest).
2. In Blender, **Edit → Preferences → Get Extensions → Install from Disk…** and choose the zip.
3. In the 3D viewport press **N** and open the **SolidCraft** tab.

## Use

1. Start SolidCraft and open a design. The control channel must be on (the default:
   **Preferences → Assistant → Let AI agents connect**).
2. Click **Connect**. The add-on reads SolidCraft's port and token files by itself; with several
   SolidCraft windows it connects to the most recently started one. **Port** and **Token** are
   only needed when Blender cannot see those files.
3. Keep **Live** on to follow every change, or turn it off and click **Refresh** when you want.

**Tessellation** sets the quality (or your own chord and angle) and the topology for the scene.
**Refacet Selected** gives the selected bodies their own settings; the ✕ next to it returns them
to the scene's.

**Tools**: **Unwrap by Faces** unwraps the selected bodies along their face boundaries;
**Select B-rep Face** grows an Edit Mode selection to whole CAD faces.

## How it works

The add-on speaks SolidCraft's control channel (JSON lines on 127.0.0.1, with the launch token):
`control.subscribe` for change events, and the `live.meshes` command for the meshes, sending the
keys of the meshes it already has. The mesh format is SolidCraft's `docs/formats/live-mesh.md`.
Only Python's standard library is used.

## Develop

```text
python -m pytest                                     # decoding, discovery and the link, no Blender
blender --background --factory-startup --python tests/blender_smoke.py   # the scene, in Blender
python tests/e2e_solidcraft.py PORT                  # the link against a running SolidCraft
blender --background --factory-startup --python tests/blender_live.py -- PORT [OUT_DIR]   # both
```

The last two change the design open in that SolidCraft: start one for them, for example
`solidcraft --sample --control 27999`.

Every push and pull request runs the CI (`.github/workflows/ci.yml`): ruff, the tests above
without Blender on Linux, Windows and macOS, and in Blender 4.2 and 5.2 the scene test, the
extension build and an install of the built zip. A pull request's zip is attached to its run.

## Release

Raise `version` in `blender_manifest.toml` and merge it into `main`: the release workflow runs
the CI, builds `solidcraft_link-<version>.zip` with Blender's `extension build`, tags `v<version>`
and publishes a GitHub release with the zip, its SHA-256 and notes from the merged pull requests.
Pushing a tag `v<version>` that matches the manifest does the same.

## Licence

GPL-3.0-or-later (see `LICENSE`), as Blender add-ons are.
