# Trusted SSH Signers

This directory contains only public trust material for Git SSH signature
verification. Private keys, passphrases, and SSH agent sockets must never be
stored in the repository.

- `allowed_signers` lists active signer principals and public keys.
- `revoked_signers` is the OpenSSH revocation file consulted during
  verification.

The repository-local Git configuration and CI validation use these files to
verify signed commits and annotated release tags. Add, rotate, or revoke a
signer through a focused, signed change request, and use the commit email
address as the signer principal. The CI validator reads these files from the
trusted parent revision, not from the change being validated. Therefore push a
trust-registry rotation separately before using the new signer. Treat changes
here as security-sensitive.
