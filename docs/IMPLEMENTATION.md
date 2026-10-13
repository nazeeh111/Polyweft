# Polyweft 0.1: review and combine native Blender mesh payloads

Original offline implementation. No separately billed API. GPL-3.0-or-later. Prior art: MeshGit (2013) and BlenDiff; no claim to invent mesh merging or correspondence. Name search on 2026-10-13 returned no GitHub repository called Polyweft; this is not a trademark search.

## Complete user workflow

Prepare a new common ancestor from a named mesh object, save two branches in Blender, capture a three-way plan, review real geometry and conflicts in a local static studio, export source-bound decisions, and apply into a fresh native `.blend`. Reopen the result and compare supported fields before publishing it. All source files remain byte-identical. An example must demonstrate this complete workflow on a meaningful original sculptural asset, shared meshes and UV seams, not just a flat grid.

The supported target is one prepared mesh and its admitted material defaults. XYZ vertices and UV corner pairs are atomic. Choose base/left/right for competing values. The destination/right scene supplies everything outside this payload, including object transforms, animation and render settings. This is prominently acknowledged in the CLI and studio; this is not a whole-scene diff. Report observed out-of-scope changes without claiming an exhaustive whole-scene inventory.

## Division of ownership

- Native/core implementer: all Python modules except studio assets, tests/test_engine.py and tests/test_native.py, tools/make_example.py, examples generated files, native receipts. Own CLI orchestration and real Blender bridge.
- Root: studio/index.html, studio/app.mjs, studio/style.css, studio geometry helper and Node tests; packaging, repository docs/workflows and release integration. No edits to native/core files while implementer works.
- Fresh reviewer: independently inspect complete artifacts and exercise consequential failure cases; save report outside repository.

## Stable interfaces

Python console script `polyweft=polyweft.cli:main`. No runtime dependency beyond standard Python and an explicit Blender executable.

`polyweft prepare SOURCE.blend --object NAME --output BASE.blend --blender EXE`

`polyweft plan BASE.blend LEFT.blend RIGHT.blend --output REVIEW_DIRECTORY --blender EXE`

`polyweft studio REVIEW_DIRECTORY --port PORT` serves loopback-only static assets and plan.json; no remote filesystem browser or mutating HTTP endpoints. Must serve only actual bundle files, reject arbitrary paths/symlinks. An offline review directory contains assets and can run through any ordinary static server.

`polyweft apply REVIEW_DIRECTORY --output MERGED.blend --decisions DECISIONS.json --accept-payload-scope --blender EXE`

Unresolved conflicts forbid output. Optional decisions if no conflicts. Fresh recomputation verifies every source hash, plan binding and each choice before any native modification. Never trust browser-proposed operations. Output must be new and separate from sources. Save temp in output parent, reopen and verify, then no-clobber publish. Use Blender factory startup, offline mode and disabled auto execution. Own fixed bridge script opens source with `use_scripts=False, load_ui=False`. No shell=True. Existing inputs and user Blender sessions untouched.

Plan JSON contract:

```
{
  "schema": "polyweft.plan.v1", "id": "sha256 of canonical immutable plan fields",
  "sources": {"base": {"path": "absolute", "sha256": "..."}, "left": {...}, "right": {...}},
  "snapshots": {"base": SNAPSHOT, "left": SNAPSHOT, "right": SNAPSHOT},
  "changes": [{"key": "vertex:ID", "domain": "vertex|uv|material", "label": "...", "kind": "left|right|same|conflict", "base": VALUE, "left": VALUE, "right": VALUE}],
  "blockers": [{"code": "...", "message": "..."}],
  "observed_exclusions": ["..."],
  "scope": "Only target mesh XYZ, UV corners and admitted material defaults are merged. Everything else comes from right. This is not a full-scene diff."
}
```

SNAPSHOT presentation contract: `name` target name; `vertices` list of `{id: integer, co: [x,y,z]}`; `faces` list of lists of vertex IDs; `uv_layers` map name to list of `{id: integer corner index, vertex: integer ID, uv:[u,v]}`; material information may have additional native fields. Native private guards may be present. JSON must be finite, bounded and strict. Preserve actual values and source provenance. Changes include all actual supported changes, not unchanged fields. Changes sorted by key. Plan may contain blockers and still be reviewed, but never applied.

Decision export: `{ "schema": "polyweft.decisions.v1", "plan_id": "...", "choices": { "vertex:ID": "base|left|right" } }`. Only choices for actual conflict keys. Invalid, unknown, stale or missing choices reject. UI never claims exported decisions are a native merged scene.

## Admission and verification

Require target mesh/vertex/object/material identities assigned before branching. Refuse missing/duplicate identities, topology changes including index reorder, target membership changes, linked/library data, shape keys and unhandled target structural changes. Preserve shared mesh aliases. Do not align arbitrary raw vertex indices. Guard UV names and counts and material graph/socket identity. Guard unsupported target mesh attributes, relevant modifier/group structure and graph changes or refuse them at prepare time. No same-vector per-axis blending. Material color/roughness operations must actually persist native files.

Fresh capture verifies result against expected payload and admitted guards; source hashes before/after. Relative paths must survive saving under a new output directory. Include a real relative texture-path case, no overwrite/alias case, manipulated plan and stale decision case. Native verification does not prove artistic quality, absence of geometry self-intersections or arbitrary Blender file safety. Reflect those boundaries in product docs.

## Delivery gates

1. Meaningful stdlib unit checks, native tests on the pinned local Blender build; package installed outside checkout.
2. Real original example branch files, conflict choices, successful apply, independent reopen, rendered image visually inspected, exact receipt.
3. Independent review of supported contract and failure behavior; fix material issues.
4. Public owned repository, actual GitHub PR and native Code Review diagnostics. Official stable Blender CI (4.5 LTS) must execute native test, not skip. Free Pages review demo with original source-bearing evidence; no fake download/apply success.
5. Versioned release with wheel, source archive and example bundle, anonymous retrieval and installed smoke/native run. Accurate topics, README, profile feature line. No third-party post without exact approval.
