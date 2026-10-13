# Security

Polyweft invokes an explicit local Blender executable and reads native scene files. Use trusted Blender builds and trusted project files. Disabling Blender script auto-execution reduces one risk; it is not a sandbox for arbitrary malicious binary files or external dependencies.

The studio serves a prepared review directory on loopback and has no native write endpoint. Review JSON and exported decisions are validated again by the CLI. Never expose the review server to a public network. Plans can contain local source paths and asset labels; review them before sharing.

Report suspected vulnerabilities through this repository's private GitHub vulnerability reporting when enabled. If that route is unavailable, open an issue asking for a private contact without including sensitive reproduction data. Do not publish an untriaged exploit.
