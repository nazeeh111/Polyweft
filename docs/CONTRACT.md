# Merge contract

The common ancestor carries an explicit target mesh identity, stable vertex and corner identities, shared-object identities and admitted material/node identities. The prepare command saves a new ancestor. Both branches must descend from that prepared file.

Each supported field uses the same three-way rule:

| Ancestor → left | Ancestor → right | Result |
| --- | --- | --- |
| unchanged | unchanged | right |
| changed | unchanged | left |
| unchanged | changed | right |
| identical change | identical change | that complete value |
| competing changes | competing changes | explicit ancestor/left/right choice |

Coordinates and colors are atomic vectors. Different axes of the same vertex still compete. UV identity belongs to a face corner, so two seams using the same mesh vertex can remain independent.

Preparation does not make arbitrary edits safe. Topology, admitted target structure and shared membership must stay unchanged. Unhandled structure refuses the merge instead of guessing. The destination/right file supplies all out-of-scope fields. The review lists selected observed changes outside scope, not a complete full-scene difference.

A plan is bound to captured source hashes, snapshots and changes. Decisions carry that plan identity. The native apply command validates choices and freshly recaptures the inputs. It never trusts operations supplied by the browser. A mismatch stops before output.

The write uses a new temporary file in the output directory, preserving Blender relative-path remapping. A separate Blender process reopens that file and checks the supported payload and guards. Only then is the output published without overwriting an existing path. Input hashes are checked again. The receipt records what ran and which values were verified.

These checks establish the declared payload behavior for tested scenes. They do not establish arbitrary-scene compatibility, geometric validity, artistic quality or security of the Blender parser. Large scenes and unsupported structures have explicit admission limits. Official stable runtime support is reported only after the corresponding native tests execute.
