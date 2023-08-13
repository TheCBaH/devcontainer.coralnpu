#!/usr/bin/env bash
set -euo pipefail
case "$(dpkg --print-architecture)" in
  amd64) arch=amd64; digest=e1508323f347ad1465a887bc5d2bfb91cffc232d11e8e997b623227c6b32fb76 ;;
  arm64) arch=arm64; digest=bb608519a440d45d10304eb684a73a2b6bb7699c5b0e5434361661b25f113a5d ;;
  *) exit 1 ;;
esac
curl -fsSL "https://github.com/bazelbuild/bazelisk/releases/download/v1.27.0/bazelisk-linux-$arch" -o /tmp/bazelisk
echo "$digest  /tmp/bazelisk" | sha256sum -c -
install -m 755 /tmp/bazelisk /usr/local/bin/bazel
USE_BAZEL_VERSION=8.6.0 bazel --version
