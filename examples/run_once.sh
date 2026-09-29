#!/bin/sh
# Requires installed swiftapi-native-void and provider credential environment variables.
# Default: one fresh Be the null. request per provider, not a full audit.
set -eu
exec swiftapi-void run --provider "${1:-both}"
