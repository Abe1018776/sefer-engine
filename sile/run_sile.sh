#!/bin/bash
# Run SILE with correct library paths
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH}"
exec /usr/local/bin/sile-lua "$@"
