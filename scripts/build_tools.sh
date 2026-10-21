#!/usr/bin/env bash
# Build the pinned CPU reference toolchain into .tools/ (gitignored):
#   Kissat     github.com/arminbiere/kissat     @ 8af8e56f174b778aef3aa45af9f739b2a5f492c2
#   drat-trim  github.com/marijnheule/drat-trim @ 2e3b2dc0ecf938addbd779d42877b6ed69d9a985
# These are the commits recorded in calibration/cpu-v0/run.json; the CPU
# harness (calibrate_cpu.py) also records each binary's sha256 in its
# campaign identity, so a different build fails its identity check instead
# of silently mixing results. Build commands match run.json provenance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/.tools"
KISSAT_COMMIT=8af8e56f174b778aef3aa45af9f739b2a5f492c2
DRAT_COMMIT=2e3b2dc0ecf938addbd779d42877b6ed69d9a985
mkdir -p "$TOOLS/logs"

fetch() {  # fetch <url> <dir> <commit>
  if [ ! -d "$2/.git" ]; then
    git clone --quiet "$1" "$2"
  fi
  git -C "$2" fetch --quiet origin
  git -C "$2" checkout --quiet "$3"
  [ "$(git -C "$2" rev-parse HEAD)" = "$3" ] || { echo "error: $2 not at $3" >&2; exit 1; }
}

fetch https://github.com/arminbiere/kissat.git "$TOOLS/kissat" "$KISSAT_COMMIT"
( cd "$TOOLS/kissat" && ./configure > "$TOOLS/logs/kissat-configure.log" 2>&1 \
  && make -j4 > "$TOOLS/logs/kissat-make.log" 2>&1 )

fetch https://github.com/marijnheule/drat-trim.git "$TOOLS/drat-trim" "$DRAT_COMMIT"
( cd "$TOOLS/drat-trim" && make drat-trim > "$TOOLS/logs/drat-trim-make.log" 2>&1 )

echo "kissat:    $TOOLS/kissat/build/kissat  sha256=$(shasum -a 256 "$TOOLS/kissat/build/kissat" | cut -d' ' -f1)"
echo "drat-trim: $TOOLS/drat-trim/drat-trim  sha256=$(shasum -a 256 "$TOOLS/drat-trim/drat-trim" | cut -d' ' -f1)"
echo "Compare with calibration/cpu-v0/run.json identity (kissat_sha256, drat_trim_sha256)."
echo "Binary hashes depend on compiler and platform; recorded runs used macOS arm64."
