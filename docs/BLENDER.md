# Polyweft inside Blender

The extension is an **unreleased preview**. Build the self-contained `polyweft-0.3.0.zip` from this source checkout using the command below, then install it through **Preferences → Get Extensions → Install from Disk**. Enable Polyweft, then open **3D View → Sidebar → Polyweft**. The ZIP contains the engine, browser inspection and license. After building it, no pip installation, system Python, account or runtime download is needed. [Current verification and remaining gate](VERIFICATION.md#native-extension-preview)

The extension targets Blender 4.5 or newer on macOS arm64 and Linux x64. It requires that Blender ships a matching standalone Python under its Python installation's `bin` directory. If that interpreter is missing or its major/minor version differs, Polyweft refuses the operation with a controlled diagnostic. Windows is unavailable in this version. Targeted platforms are not a claim that every Blender/platform combination has been tested; see the release verification record.

## From saved branches to a saved merge

1. **Prepare before branching.** Select a saved trusted `.blend`, enter the exact target mesh object name, and choose a new prepared-copy path. Preparing adds durable mesh identities to a new copy and verifies it by reopening it. Make both branches from this prepared ancestor. An existing arbitrary unprepared branch cannot acquire correspondence retrospectively.
2. **Choose the ancestor, left and right saved files.** Right supplies the destination scene. Create a branch review. Blender's editor stays responsive while a separately owned process captures and checks the files. Unsaved edits in the active scene are not included.
3. **Choose each competing whole value.** Select a row to see its exact stored ancestor, left and right values. Choose one complete value; coordinates, UV corners and material values are not mixed per component. Independent edits combine automatically. Structural blockers and incomplete choices prevent inspection and saving.
4. **Inspect these choices.** Open the read-only four-state view to compare ancestor, left, right and the combination. This browser snapshot has one decision authority: the choices in the Blender panel. It cannot change/import/export decisions. A conflict-free merge can still produce an intersecting or unwanted surface. Inspection reports this; it does not repair it.
5. **Accept the displayed payload scope.** Only admitted target-mesh coordinates, UV corners and material defaults are merged. Everything else comes from right. Select a new merged-copy path, then verify and save. Polyweft recaptures sources, saves a fresh copy, reopens and checks its supported payload, rechecks source bytes, and only then publishes without replacing an existing path.

Changing selected sources, saved-file identity, size, modification time or any whole-value choice invalidates inspection and closes its owned server. Saving requires a fresh inspection and renewed scope acceptance. File metadata is an early invalidation hint; permissions and last-used metadata alone do not indicate a saved edit. A rewrite that preserves those monitored fields may evade this hint. The engine's source hashes and fresh captures remain the authoritative checks. The add-on never automatically saves, opens or replaces the editor's current scene. The saved copy remains on disk until you explicitly open it.

## Recovery and cancellation

Every operation creates a new folder under Blender's extension user directory. **Open recovery folder** reveals `request.json`, atomic `status.json`, `worker.log`, and any locally generated `decisions.json`. Reviews and inspections have their own new output folders alongside jobs. The panel shows the verified output path after completion. These folders are retained on failure and cancellation; they can contain private local paths, object labels and captured values, so inspect them before sharing.

After restarting Blender, select the same three saved sources and the saved review directory, then **Reload saved review**. Loading verifies the saved plan and its binding to the selected source paths. Select whole values again and create a fresh inspection. Loading a plan does not establish that its source bytes are still current; inspection and saving revalidate them through the engine.

**Cancel and wait** requests cancellation without blocking Blender's editor. Controls remain frozen until that worker actually exits. A worker stops and reaps only the native children it created. A verified output already published before cancellation remains completed. No output is deleted or overwritten. Disabling the add-on closes its worker pipes, requests cancellation and retains process ownership in a cleanup timer until workers exit. **Close inspection server** ends the owned localhost server; an already loaded browser page is only a retained snapshot.

Use trusted local assets and a trusted Blender installation. Auto-execution is disabled for native loads, but Blender is not a hostile-file sandbox. Unchanged topology and prepared identities remain mandatory. Linked data, shape keys and unsupported structure stay refused. The extension adds a native workflow, not a whole-scene merge or a new merge algorithm.

## Build from source

With Python 3.11 or newer, run:

```sh
python tools/build_extension.py --output dist/polyweft-0.3.0.zip
```

The destination ZIP must be new. The builder bundles current `src/polyweft` bytes as `_engine`, including studio assets, plus the extension and existing GPL license. `PACKAGE-MANIFEST.json` lists the SHA-256 hash of every other archive member. Sorted member order, fixed timestamps and fixed file modes make repeated builds from identical bytes reproducible. No packages are fetched or installed. The extension's standalone worker launcher executes only its bundled fixed workflow dispatcher.
