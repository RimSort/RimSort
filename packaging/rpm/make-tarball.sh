#!/bin/bash
# Create source tarball with submodules for RPM building

set -e

VERSION="${1:-1.0.63}"
TARBALL="$HOME/rpmbuild/SOURCES/rimsort-$VERSION.tar.gz"

echo "Creating source tarball with submodules..."

# Create temporary directory
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Archive main repository
git archive --prefix="RimSort-$VERSION/" HEAD | tar -x -C "$TMPDIR"

# Archive submodules
git submodule foreach --quiet 'git archive --prefix="RimSort-'"$VERSION"'/$displaypath/" HEAD | tar -x -C "'"$TMPDIR"'"'

# Create the final tarball
cd "$TMPDIR"
tar -czf "$TARBALL" "RimSort-$VERSION"

echo "Tarball created: $TARBALL"
ls -lh "$TARBALL"
