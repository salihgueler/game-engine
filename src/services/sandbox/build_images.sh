#!/bin/sh
# Build sandbox container images using Finch
# Usage: ./build_images.sh

set -e

SCRIPT_DIR="$(dirname "$0")"
DOCKERFILE_DIR="$SCRIPT_DIR/dockerfiles"

echo "Building Python sandbox image..."
docker build -t quest-sandbox-python:latest -f "$DOCKERFILE_DIR/Dockerfile.python" "$DOCKERFILE_DIR"

echo "Building Java sandbox image..."
docker build -t quest-sandbox-java:latest -f "$DOCKERFILE_DIR/Dockerfile.java" "$DOCKERFILE_DIR"

echo "Building TypeScript sandbox image..."
docker build -t quest-sandbox-typescript:latest -f "$DOCKERFILE_DIR/Dockerfile.typescript" "$DOCKERFILE_DIR"

echo "All sandbox images built successfully."
docker images | grep quest-sandbox
