#!/usr/bin/env bash
set -euo pipefail
version=${VERSION:-9.1.0}
case "$(dpkg --print-architecture)" in
  amd64) arch=x86_64 ;;
  arm64) arch=arm64 ;;
  *) exit 1 ;;
esac
case "$version-$arch" in
  9.1.0-x86_64) digest=a667454f3f4f8878df8199136b82c199f6ada8477b337fae3b1ef854f01e4e2f ;;
  9.1.0-arm64) digest=ba933bfc943e4c44f0743a5823aa2312a34b39628532add5dd037e08d8ec27a4 ;;
  *) echo "No pinned digest for Bazel $version on $arch" >&2; exit 1 ;;
esac
binary=bazel-$version-linux-$arch
curl -fsSL "https://github.com/bazelbuild/bazel/releases/download/$version/$binary" -o "/tmp/$binary"
echo "$digest  /tmp/$binary" | sha256sum -c -
install -m 755 "/tmp/$binary" /usr/local/bin/bazel
rm "/tmp/$binary"
