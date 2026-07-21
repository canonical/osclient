#!/usr/bin/env bash
#
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Check the codebase for non-ascii characters

out=$(for filetype in 'py' 'sh' 'md'; do
    LC_ALL=C find . -name "*.$filetype" -not -path './.*' -exec grep -nHP "[\x80-\xFF]" {} \;
done)
if [ -n "$out" ]; then
    printf "Non-ascii characters detected in code:\n%s" "$out"
    exit 1
fi
