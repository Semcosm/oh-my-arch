# The minimal profile currently uses the shared archiso defaults. Keep this
# file self-contained because archiso evaluates it from a temporary profile.
iso_name="${OMA_ISO_NAME:-oh-my-arch}"
iso_label="${OMA_ISO_LABEL:-OHMYARCH}"
iso_publisher="Oh My Arch"
iso_application="Oh My Arch live image"
iso_version="${OMA_VERSION:-development}"
install_dir="arch"
buildmodes=("iso")
bootmodes=("bios.syslinux" "uefi.systemd-boot")
arch="${OMA_ARCH:-x86_64}"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
