# v0.1.0

Canonical source mirror of
[swiftapi-native-void 0.1.0 on PyPI](https://pypi.org/project/swiftapi-native-void/0.1.0/).

The package source, tests, build configuration, protocol, license, and root README
match the published source distribution byte-for-byte. Repository additions are
`.github/`, `examples/`, `.gitignore`, and this release note. No package behavior,
prompts, model identifiers, token limits, or classification semantics changed.

The [GitHub release](https://github.com/theonlypal/swiftapi-native-void/releases/tag/v0.1.0)
attaches the original PyPI wheel and sdist, not renamed or rebuilt substitutes.
The annotated `v0.1.0` tag identifies the release commit; its full SHA is also
recorded in the release notes and attached `release-manifest.json`.

| File | SHA-256 |
| --- | --- |
| `swiftapi_native_void-0.1.0-py3-none-any.whl` | `44047fc7611b42d4a8660fda9617116c2ce211342e686aaa612708e7403b5a7c` |
| `swiftapi_native_void-0.1.0.tar.gz` | `071e786bc058b000aea54029daca3afa601b9f5b6932db40b8d872d3b0d7bb50` |

Frozen protocol SHA-256:

```text
4446b3f0313d4cfc777d4f40e3f2f52a2c5bb80cb207b52aef08e7ce777c8cff
```

Verify the mirror without inference:

```bash
python .github/verify_release.py
```

Rebuild with the pinned build requirements:

```bash
python scripts/build_release.py
python -m twine check dist/*.whl dist/*.tar.gz
python .github/verify_release.py --built dist
```

GitHub's automatically generated source ZIP/tar archives include repository
infrastructure and are distinct from the attached PyPI sdist.

PyPI 0.1.0 metadata predates this repository and remains unchanged. No new PyPI
version was published to add a backlink. GitHub links directly to the existing
PyPI release and public research evidence.
