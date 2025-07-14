#!/bin/bash

echo "Checking for cdxgen..."

if command -v cdxgen &> /dev/null; then
  echo "cdxgen is already installed."
  exit 0
fi

# Detect OS type
OS_TYPE="$(uname -s)"

# macOS: Try Homebrew
if [[ "$OS_TYPE" == "Darwin" ]]; then
  echo "Detected macOS"

  if command -v brew &> /dev/null; then
    echo "Installing cdxgen via Homebrew..."
    brew install cdxgen
    exit $?
  else
    echo "Homebrew not found. Trying npm..."
  fi

# Linux: Fall back to npm
elif [[ "$OS_TYPE" == "Linux" ]]; then
  echo "Detected Linux"
  echo "Installing cdxgen via npm..."

# Windows via Git Bash, WSL, or MSYS
elif [[ "$OS_TYPE" == MINGW* || "$OS_TYPE" == CYGWIN* || "$OS_TYPE" == MSYS* ]]; then
  echo "Detected Windows (Unix shell)"

  if command -v winget &> /dev/null; then
    echo "Installing cdxgen via winget..."
    winget install cdxgen
    exit $?
  else
    echo "winget not found. Trying npm..."
  fi
else
  echo "Unknown OS: $OS_TYPE. Trying npm as fallback..."
fi

# Final fallback: npm
if command -v npm &> /dev/null; then
  echo "Installing cdxgen via npm..."
  npm install -g @cyclonedx/cdxgen
else
  echo "npm not found. Please install Node.js or use a supported package manager."
  exit 1
fi

echo "cdxgen installation complete."


# chmod +x tools-setup.sh
# ./tools-setup.sh