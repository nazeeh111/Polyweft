# Polyweft

**Both branches had separated surfaces. Their merge crossed.** On the prepared Blender mesh below, two independent edits merged without a value conflict but created **20 crossing face pairs**. Changing the right branch’s translation from **−3 X to −1 X** brought the count to **0** on the inspected target faces. The revised Blender file was saved and reopened.

[Try the crossing case in your browser](https://nazeeh111.github.io/Polyweft/interference/) · [Download the Blender extension preview](https://github.com/nazeeh111/Polyweft/releases/download/v0.3.0-preview.1/polyweft-0.3.0.zip)

<picture>
  <source media="(max-width: 650px)" srcset="docs/presentation/revision-compact.svg">
  <img src="docs/presentation/revision.png" alt="The same two Blender surfaces at the same camera angle and scale. Their original merge has 20 crossing face pairs and a marked crossing witness. Revising the right translation to minus 1 X yields zero in the represented target-face inspection.">
</picture>

The image projects the recorded native triangles and highlights one exact crossing witness. [Replay the native branch revision](docs/presentation/README.md) · [Inspect the exact geometry](docs/presentation/revised-inspection.json) · [Open the recorded phone workbench](docs/presentation/revised-375.png)

<details>
<summary>Original workbench walkthrough</summary>

<picture>
  <source media="(max-width: 650px)" srcset="docs/interference-mobile.gif">
  <img src="docs/interference-walkthrough.gif" alt="Read-only Polyweft browser studio displaying ancestor, left, right and configured merge for the crossing-surface case.">
</picture>

The recorded inspection used Blender 4.5.14. [Recording and source identities](docs/PRESENTATION.md) · [Resolve competing edits in the browser](https://nazeeh111.github.io/Polyweft/)

</details>

## Run the native workflow

Python 3.11+ and a trusted local Blender executable are required. There are no Python runtime dependencies, accounts or model services.

```sh
python -m pip install .
polyweft prepare model.blend --object Shell --output base.blend --blender /path/to/blender
# Branch from prepared base.blend, then save left.blend and right.blend.
polyweft plan base.blend left.blend right.blend --output review --blender /path/to/blender
polyweft studio review --port 0
```

In this source preview, the browser is read-only. Use the native extension panel below for whole-value choices, or supply decisions.json to the existing CLI. The browser compares captured geometry; it does not save Blender files.

```sh
polyweft inspect review --decisions decisions.json --output inspected --blender /path/to/blender
polyweft studio inspected --port 0
polyweft apply review --decisions decisions.json --output merged.blend \
  --accept-payload-scope --blender /path/to/blender
```

Omit decisions for a conflict-free plan. Inspect again after changing choices or branch geometry. Inspection neither saves a scene nor gates apply; native apply separately rechecks exact sources and payload, saves a new file and freshly reopens it. Existing outputs, changed sources, unresolved conflicts and unsupported structure are refused.

## Work inside Blender · extension preview

The new native panel brings saved-file selection, whole-value choices, inspection and verified saving into Blender. It uses Blender's bundled Python, so the installed extension needs no pip, system Python or executable-path setup. Your active scene stays untouched. The browser becomes a read-only inspection snapshot; choices stay in the Blender panel.

[Download the extension ZIP](https://github.com/nazeeh111/Polyweft/releases/download/v0.3.0-preview.1/polyweft-0.3.0.zip) or [see the preview release and checksum](https://github.com/nazeeh111/Polyweft/releases/tag/v0.3.0-preview.1). The installed operator workflow passed on Blender 5.2.1 LTS for macOS arm64 and on Blender 4.5.14 LTS for Linux x64. Hands-on panel acceptance is pending. [Verification status](docs/VERIFICATION.md#native-extension-preview)

Install it through **Preferences → Get Extensions → Install from Disk**, enable Polyweft, then open **3D View → Sidebar → Polyweft**.

1. Prepare a saved ancestor before branching, then choose the ancestor, left and right files.
2. Create a review and choose each competing whole value in the panel.
3. Inspect the four saved states in the read-only browser view.
4. Accept the limited payload scope and save to a new merged-copy path.

Changing a choice or a monitored source-file property revokes the inspection and scope acceptance. Saving always rechecks source hashes and native captures. The extension targets macOS arm64 and Linux x64 with Blender 4.5+ and its matching bundled standalone Python; Windows is unavailable. [Full native workflow, recovery and cancellation](docs/BLENDER.md)


## Scope

- Reconcile complete XYZ vectors, per-corner UV pairs and admitted Principled Base Color/Roughness inputs. It never mixes coordinate axes to invent a value.
- Prepare before branching; retain durable identities and unchanged topology. Outside the admitted payload, **everything comes from right**. This is not a whole-scene merge or arbitrary mesh correspondence.
- Surface inspection covers distinct native target polygon faces in object-local coordinates. Incomplete coverage never establishes separation. Other objects, solid containment, within-face folding, evaluated modifiers, artistic intent and physical tolerances remain outside scope.

The recorded revision ran on installed **Blender 5.1.2**, with 33 native/core Python tests and 13 Node tests passing. Extension verification is recorded separately above. Blender auto-execution is disabled; a trusted executable and trusted artwork are still required.

[Full original guide](TECHNICAL_GUIDE.md) · [Merge contract](docs/CONTRACT.md) · [Inspection limits](docs/INTERFERENCE.md) · [Original verification](docs/VERIFICATION.md) · [Contributing](CONTRIBUTING.md).

Licensed [GPL-3.0-or-later](LICENSE). User artwork and data remain their authors' property. No hardware or fabrication claim.
