#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR=${1:?kernel source directory}
OUT_DIR=${2:?kernel output directory}
TOOLCHAIN_DIR=${3:?Android clang directory}
JOBS=${4:-4}

export PATH="$TOOLCHAIN_DIR/bin:$PATH"
export ARCH=arm64 LLVM=1 LLVM_IAS=1
export CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export KBUILD_BUILD_USER=galaxy-watch-root KBUILD_BUILD_HOST=github-actions
export KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='Thu Jan  1 00:00:00 UTC 1970'
export SOURCE_DATE_EPOCH=0 KCONFIG_NOTIMESTAMP=1
# Device-specific values come from the checked-in configuration through the
# environment. The defaults keep this script useful for the Watch 7 config.
export BRANCH=${BRANCH:-android14-6.1}
export KMI_GENERATION=${KMI_GENERATION:-11}
export TARGET_BUILD_VARIANT=${TARGET_BUILD_VARIANT:-user}
export TARGET_SOC=${TARGET_SOC:-s5e5535}
export TARGET_PRODUCT=${TARGET_PRODUCT:-fresh7ulxx}
export KERNEL_RELEASE_SUFFIX=${KERNEL_RELEASE_SUFFIX:--android14-11}
export KCFLAGS=-D__ANDROID_COMMON_KERNEL__

mkdir -p "$OUT_DIR"
printf '%s\n' "$KERNEL_RELEASE_SUFFIX" > "$SOURCE_DIR/.scmversion"
make -C "$SOURCE_DIR" O="$OUT_DIR" olddefconfig
release=$(make --no-print-directory -s -C "$SOURCE_DIR" O="$OUT_DIR" kernelrelease)
make -C "$SOURCE_DIR" O="$OUT_DIR" -j"$JOBS" Image
test -s "$OUT_DIR/arch/arm64/boot/Image"
sha256sum "$OUT_DIR/arch/arm64/boot/Image" > "$OUT_DIR/Image.sha256"
printf '%s\n' "$release" > "$OUT_DIR/kernelrelease"
echo "Built $release"
