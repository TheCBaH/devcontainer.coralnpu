#!/usr/bin/env bash
set -euo pipefail
mkdir -p /opt/firtool/bin
# Upstream distributes firtool for Linux x86_64 only.
if [ "$(dpkg --print-architecture)" != arm64 ]; then exit 0; fi
curl -fsSL https://github.com/llvm/circt/releases/download/firtool-1.114.0/circt-full-sources.tar.gz -o /tmp/circt.tar.gz
echo '278c822cb483b2d825e3a4eb8be0422f130bf466fc0eb50c23c222546db07c40  /tmp/circt.tar.gz' | sha256sum -c -
mkdir /tmp/circt
tar -xzf /tmp/circt.tar.gz -C /tmp/circt
cmake -G Ninja -S /tmp/circt/llvm/llvm -B /tmp/circt-build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-19 -DCMAKE_CXX_COMPILER=clang++-19 \
  -DLLVM_ENABLE_PROJECTS=mlir -DLLVM_EXTERNAL_PROJECTS=circt \
  -DLLVM_EXTERNAL_CIRCT_SOURCE_DIR=/tmp/circt -DLLVM_TARGETS_TO_BUILD=Native \
  -DLLVM_ENABLE_ASSERTIONS=OFF -DLLVM_ENABLE_BINDINGS=OFF \
  -DLLVM_INCLUDE_TESTS=OFF -DMLIR_INCLUDE_TESTS=OFF -DCIRCT_INCLUDE_TESTS=OFF
cmake --build /tmp/circt-build --target firtool --parallel 2
install /tmp/circt-build/bin/firtool /opt/firtool/bin/firtool
install /tmp/circt/LICENSE /opt/firtool/LICENSE
