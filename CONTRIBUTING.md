# Contributing

Start with a reproducible artist workflow or a minimal `.blend` created from your own assets. Do not upload confidential scenes or textures. Explain the common ancestor, intended supported edit, expected result and actual receipt.

The supported merge is deliberately narrow. Changes to correspondence, admission or native write-back need an executable failure case and a fresh reopened-file check. Do not replace guards with index-based guesses.

Run `python -m unittest discover -s tests -v` and `node --test tests/*.test.mjs`. Set `POLYWEFT_BLENDER` to a Blender executable to run native tests. The release gate requires those tests to run, not skip.

AI-assisted contributions are welcome when the contributor understands the patch, can explain its boundaries and takes responsibility for the evidence. Label generated examples and retain provenance and licenses. Review comments should identify concrete behavior, not manufacture activity.
