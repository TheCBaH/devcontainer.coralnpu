FROM ubuntu:24.04 AS tools
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key | gpg --dearmor -o /usr/share/keyrings/llvm.gpg && \
    echo 'deb [signed-by=/usr/share/keyrings/llvm.gpg] https://apt.llvm.org/noble/ llvm-toolchain-noble-19 main' > /etc/apt/sources.list.d/llvm.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    autoconf automake bison build-essential ccache clang-19 clang-tools-19 \
    cmake device-tree-compiler flex gawk git libelf-dev libffi-dev liblz4-dev \
    libmpfr-dev libtinfo-dev libzstd-dev lld-19 llvm-19 ninja-build \
    openjdk-21-jdk-headless patchelf pkg-config python3 python3-dev \
    python3-numpy python3-pip python3-venv rsync shellcheck srecord sudo \
    unzip zip zlib1g-dev && find /var/lib/apt/lists -mindepth 1 -delete
RUN for tool in clang clang++ clang-cpp llvm-ar llvm-nm llvm-objcopy llvm-strip; do \
      ln -s /usr/bin/$tool-19 /usr/local/bin/$tool; done && \
    ln -s /usr/bin/ld.lld-19 /usr/local/bin/ld.lld
COPY install-tools.sh /tmp/install-tools.sh
RUN bash /tmp/install-tools.sh
FROM tools AS firtool-builder
COPY build-firtool.sh /tmp/build-firtool.sh
RUN bash /tmp/build-firtool.sh
FROM tools
COPY --from=firtool-builder /opt/firtool /opt/firtool
RUN if id ubuntu >/dev/null 2>&1; then userdel ubuntu; fi
ENV PATH=/opt/firtool/bin:$PATH
