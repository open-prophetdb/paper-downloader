#!/bin/bash

set -e

VERSION=$(git describe --tags `git rev-list --tags --max-count=1` --always)

# dynamically pull more interesting stuff from latest git commit
HASH=$(git show-ref --head --hash=8 head)  # first 8 letters of hash should be enough; that's what GitHub uses

# Change the version in the setup.py
TRIMMED_VERSION=$(echo $VERSION | sed 's/^v//')
# If running on macOS, use sed -i '' instead of sed -i
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i "" "s/version=\"0.1.0\"/version=\"${TRIMMED_VERSION}\"/g" setup.py
else
  sed "s/version=\"0.1.0\"/version=\"${TRIMMED_VERSION}\"/g" setup.py
fi

# Build standalone docker image
docker build -t paper-downloader:${VERSION}-${HASH} . && \

if [ "$1" == "--push" ]; then
  docker tag paper-downloader:${VERSION}-${HASH} ghcr.io/yjcyxky/paper-downloader:${VERSION}-${HASH} && \
  docker push ghcr.io/yjcyxky/paper-downloader:${VERSION}-${HASH}
fi