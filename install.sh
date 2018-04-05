#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/"
DEST="$HOME/Library/Application Support/Sublime Text 3/Packages/multi-formatter"

npm install standard prettier sort-package-json -g

ln -fs "$DIR" "$DEST"

