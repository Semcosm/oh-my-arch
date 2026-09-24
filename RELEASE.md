# Release Guide

Releases use trusted, SSH-signed annotated semantic-version tags and the UGS
release workflow. Add `releases/vX.Y.Z.md`, then create the tag with:

    git tag -s vX.Y.Z -m "Oh My Arch vX.Y.Z"
    git push origin vX.Y.Z

The release workflow restores and verifies the annotated tag against the
`keys/allowed_signers` and `keys/revoked_signers` snapshot from the tagged
commit's first parent before it builds or publishes ISO artifacts. This keeps a
tagged commit from adding a signer and using that signer on its own tag.

Signer rotation is intentionally two-step: push the signed trust-registry
change first, then create and push a signed tag (or commit) in a later push.
The local check is:

    scripts/validate_release_tag.sh vX.Y.Z
