# Test scripts

Tests here validate the build model without requiring a privileged Arch build
host where possible.

The ISO boot smoke test needs qemu-system-x86_64, OVMF firmware, and
tesseract. Run it against a built image with:

    python3 scripts/test/test_iso_boot.py output/oh-my-arch-minimal-x86_64-0.0.1.iso

It checks both BIOS and UEFI boot paths and waits for the root@oh-my-arch live
shell prompt. OMA_BOOT_TIMEOUT sets the per-mode timeout in seconds; it
defaults to 180.
