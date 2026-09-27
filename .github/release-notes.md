## Install

| Distribution | Package | Install with |
| --- | --- | --- |
| Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pop!_OS 22.04+ | `stallion_@VERSION@-1_amd64.deb` | `sudo apt install ./stallion_@VERSION@-1_amd64.deb` |
| Fedora, openSUSE Tumbleweed | `stallion-@VERSION@-1.x86_64.rpm` | `sudo dnf install ./stallion-@VERSION@-1.x86_64.rpm` or `sudo zypper install --allow-unsigned-rpm ./stallion-@VERSION@-1.x86_64.rpm` |
| Arch, Manjaro, EndeavourOS | `stallion-@VERSION@-1-x86_64.pkg.tar.zst` | `sudo pacman -U ./stallion-@VERSION@-1-x86_64.pkg.tar.zst` |
| Any other distribution with glibc 2.35+ | `stallion-@VERSION@-linux-x86_64.tar.gz` | unpack it and run `./stallion`, or `./install.sh` to add it to your menu |
| Docker or a home server (amd64, arm64) | `ghcr.io/lam1623/stallion-python:@VERSION@` | `docker pull ghcr.io/lam1623/stallion-python:@VERSION@` |

Your package manager installs FFmpeg along with Stallion. Every package was installed and tried on fresh Ubuntu 24.04, Ubuntu 22.04, Debian 12, Fedora 42, openSUSE Tumbleweed and Arch containers before this release; `SHA256SUMS` lists their checksums.
