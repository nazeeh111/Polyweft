# Verification and limits

The release gate uses real Blender files and actual processes. No browser animation substitutes for native merging.

## Four-state inspection

The 0.2 release workflow runs 29 Python tests and 13 Node controls, with official Blender 4.5.14 LTS on Linux under Python 3.11 and 3.14. Locally, all 29 Python tests executed with the pinned Blender 5.3 Alpha build and no skipped native gate; all 13 Node controls passed. The workflow also generates and packages both original native examples.

Fresh independent review ran the 14 new numerical/native tests, checked 492 triangle pairs against a separate exact intersection test with permutation controls, and forced time, candidate and report budgets. It verified actual nonplanar quad and changing concave/convex native tessellation using a separate direct Blender query. A report-coverage display defect was reproduced, fixed and independently rechecked: omitted triangles, contradictory complete flags, unknowns, truncation and altered report bytes now refuse. Checksums establish integrity rather than authenticity.

The actual browser changed a native `vertex:9` conflict from right to left: recorded counts and face witnesses became stale/disabled immediately, while export retained the newly chosen left value. Returning to right restored the matching report. The conflict-free original Flanges case has 20 crossing pairs only in the combined native surface. Its saved merged file freshly reopened with exactly the surface used by inspection, and the original source bytes were unchanged.

The original Tide scene also completed inspection: 224 quad faces, 448 native triangles, 907 candidate polygon pairs and 14,512 exact triangle-pair tests, with no observed crossings, overlaps, contacts or unknown faces in that specific four-state case. This does not establish physical clearance, artistic quality or universal predicate correctness. See [the represented-surface contract](INTERFERENCE.md).

## Native merge foundation

- **Original 0.1 installed wheel:** all 12 package/resource files matched source bytes. Fifteen Python tests executed with the pinned Blender 5.3 Alpha build, including six native integration cases and three actual HTTP boundary cases. Five Node checks passed.
- **Original 0.1 stable-runtime gate:** Linux CI downloaded official Blender 4.5.14 LTS, checked the vendor SHA256 and executed all 15 Python and five Node checks under Python 3.11 and 3.14. The Python 3.11 job generated a new native example and portable source-bearing ZIP. Native tests did not skip.
- **Independent review:** the reviewer used separate actual native branch fixtures, reproduced shader mute and active-UV-map admission gaps, verified refusal after fixes, and tested 132 concave/collinear display cases. Plain Blender reopened the final published output and separately prepared file without the merge bridge's path normalization. Texture references resolved to original bytes, shared users and destination metadata survived, and input hashes stayed unchanged.
- **Real studio workflow:** actual browser controls selected left material roughness, right UV and ancestor XYZ. Exported JSON was re-bound through a freshly captured local plan and applied by the installed package from outside the repository. The new native output passed fresh reopen checks. A portable public plan with redacted file paths requires local capture before native apply.
- **Original scene:** Tide uses 256 vertices, 224 quad faces and two objects sharing the mesh. It has 40 supported edits and three conflicts across vertex, UV and material domains. The ribbon parameterization is periodic across the wrap. A real Cycles CPU render was visually inspected; its producer is `tools/render_example.py`.

Existing native source/output aliases, no scope acknowledgement, unresolved/unknown/stale choices, manipulated/rehashed changes, missing identities and unsupported target structure refuse without a native output. Shape keys and linked target data are refused. UV render/clone selection, supported node semantics and other guarded target attributes cannot be silently merged.

The target admission limits are 20,000 vertices, 20,000 faces, 80,000 corners (including all UV layers), eight material slots and 32 nodes per target material. These are resource bounds, not promises of performance on every scene. The studio uses a bounded dominant-axis triangulation for concave display; degenerate or overly complex faces are visibly omitted. Nonplanar display and Blender's exact native tessellation can differ.

This does not establish arbitrary unprepared-scene correspondence, topology-changing merge, full-scene difference coverage, artistic quality, geometric validity or Blender parser security. All fields outside the admitted payload come from the right scene. Windows and official macOS stable Blender combinations remain untested. External asset path preservation is checked; arbitrary external-file content/version changes are not inferred as merge edits.
