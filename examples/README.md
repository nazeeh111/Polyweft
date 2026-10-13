# Tide: two artists, one native mesh

The original Tide example has 256 vertices, 224 quad faces, two objects sharing the same mesh, and a seam-aware UV layer. Its branches contain 40 supported edits and three competing values: one XYZ vector, one UV corner and material roughness. Destination metadata and a real relative PNG reference are preserved.

The generator is [tools/make_example.py](../tools/make_example.py). It creates real `.blend` files, prepares the ancestor, produces both edits, computes the review, chooses left for the three conflicts, applies the merge and reopens the final published files to verify actual texture paths and bytes.

```sh
python tools/make_example.py --blender /path/to/blender --output tide-native
```

The output directory must be new. Downloadable native fixtures are published as a release asset after the official stable Blender generation gate passes. The browser demo is a frozen review of those actual native branch files. It does not write a Blender scene.
