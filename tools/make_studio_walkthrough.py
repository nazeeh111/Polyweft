"""Encode retained actual studio captures; never draw or infer mesh geometry.

Requires Pillow for presentation generation only, not the Polyweft runtime.
Capture actions, source identities and software versions: docs/PRESENTATION.md.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    from PIL import Image

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, default=Path('docs/captures'))
    parser.add_argument('--output', type=Path, default=Path('docs'))
    args = parser.parse_args()
    groups = {
        'interference-walkthrough.gif': ['01-combined.jpg', '02-left-alone.jpg', '03-right-alone.jpg', '04-combined-witness.jpg'],
        'interference-mobile.gif': ['12-mobile-ancestor.jpg', '13-mobile-left.jpg', '14-mobile-right.jpg', '15-mobile-combined-restored.jpg'],
    }
    records = {}
    for name, inputs in groups.items():
        frames = [Image.open(args.captures / f).convert('RGB') for f in inputs]
        if len({im.size for im in frames}) != 1:
            raise ValueError('Capture dimensions must match within each recording')
        palette = frames[0].quantize(colors=128)
        indexed = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in frames]
        durations = [4000, 4000, 4000, 6000]
        indexed[0].save(args.output / name, save_all=True, append_images=indexed[1:],
                        duration=durations, loop=0, disposal=2, optimize=False)
        records[name] = {'captures': inputs, 'duration_ms': durations,
                         'size': frames[0].size,
                         'capture_sha256': {f: hashlib.sha256((args.captures/f).read_bytes()).hexdigest() for f in inputs}}
    (args.output/'walkthrough-record.json').write_text(json.dumps(records, indent=2)+'\n')
    print('Encoded two 18-second walkthroughs from actual studio screenshots')


if __name__ == '__main__':
    main()
