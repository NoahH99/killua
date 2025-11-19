#!/bin/bash

# Docker Build and Push Script for Killua Bot
# Usage: ./docker-build-push.sh [OPTIONS]
# Options:
#   -r, --repo REPO       Docker Hub repository (e.g., username/killua-bot)
#   -t, --tag TAG         Version tag (default: latest)
#   -p, --push            Push to Docker Hub after building
#   --no-cache            Build without cache
#   --multi-arch          Build for multiple architectures (amd64, arm64)
#   -d, --debug           Enable debug output
#   -h, --help            Show this help message

set -e  # Exit on error

# Default values
REPO=""
TAG="latest"
PUSH=false
NO_CACHE=""
MULTI_ARCH=false
DEBUG=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_debug() {
    if [ "$DEBUG" = true ]; then
        echo -e "${YELLOW}[DEBUG]${NC} $1"
    fi
}

# Show help
show_help() {
    cat << EOF
Docker Build and Push Script for Killua Bot

Usage: ./docker-build-push.sh [OPTIONS]

Options:
    -r, --repo REPO       Docker Hub repository (e.g., username/killua-bot)
    -t, --tag TAG         Version tag (default: latest)
    -p, --push            Push to Docker Hub after building
    --no-cache            Build without cache
    --multi-arch          Build for multiple architectures (amd64 + arm64 for Raspberry Pi)
                          Note: Multi-arch builds require --push flag (cannot load locally)
    -d, --debug           Enable debug output with verbose logging
    -h, --help            Show this help message

Examples:
    # Build for current platform only (no push)
    ./docker-build-push.sh -r username/killua-bot

    # Build with version tag
    ./docker-build-push.sh -r username/killua-bot -t v1.0.0

    # Build and push (single platform)
    ./docker-build-push.sh -r username/killua-bot -t v1.0.0 -p

    # Build multi-arch for x86 + Raspberry Pi and push
    ./docker-build-push.sh -r username/killua-bot -t v1.0.0 -p --multi-arch

    # Build multi-arch without cache
    ./docker-build-push.sh -r username/killua-bot --no-cache -p --multi-arch

    # Build with debug output to troubleshoot issues
    ./docker-build-push.sh -r username/killua-bot -t v1.0.0 -p --debug

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--repo)
            REPO="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --multi-arch)
            MULTI_ARCH=true
            shift
            ;;
        -d|--debug)
            DEBUG=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate repository is provided
if [ -z "$REPO" ]; then
    print_error "Repository name is required!"
    echo ""
    show_help
    exit 1
fi

print_debug "Script directory: $SCRIPT_DIR"
print_debug "Arguments parsed - REPO=$REPO, TAG=$TAG, PUSH=$PUSH, MULTI_ARCH=$MULTI_ARCH, NO_CACHE='$NO_CACHE', DEBUG=$DEBUG"

# Validate multi-arch requires push
if [ "$MULTI_ARCH" = true ] && [ "$PUSH" = false ]; then
    print_error "Multi-architecture builds require the --push flag!"
    print_error "Multi-arch images cannot be loaded locally, they must be pushed to a registry."
    echo ""
    show_help
    exit 1
fi

# Construct full image name
IMAGE_NAME="${REPO}:${TAG}"

print_info "Starting Docker build process..."
print_info "Repository: $REPO"
print_info "Tag: $TAG"
print_info "Full image name: $IMAGE_NAME"
if [ "$MULTI_ARCH" = true ]; then
    print_info "Multi-arch build: linux/amd64, linux/arm64 (Raspberry Pi)"
else
    print_info "Single platform build (current architecture)"
fi

# Check if Dockerfile exists
if [ ! -f "$SCRIPT_DIR/Dockerfile" ]; then
    print_error "Dockerfile not found in $SCRIPT_DIR"
    exit 1
fi
print_debug "Dockerfile found at: $SCRIPT_DIR/Dockerfile"

# Show Docker buildx info in debug mode
if [ "$DEBUG" = true ]; then
    print_debug "Docker version:"
    docker version --format '  Client: {{.Client.Version}}, Server: {{.Server.Version}}' || true
    print_debug "Docker buildx version:"
    docker buildx version || true
    print_debug "Available builders:"
    docker buildx ls || true
fi

# Check if logged in to Docker Hub (needed for multi-arch or push)
if [ "$MULTI_ARCH" = true ] || [ "$PUSH" = true ]; then
    print_debug "Checking Docker Hub login status..."
    if ! docker info | grep -q "Username"; then
        print_warning "Not logged in to Docker Hub. Attempting to log in..."
        if ! docker login; then
            print_error "Docker login failed!"
            exit 1
        fi
    else
        USERNAME=$(docker info | grep Username | awk '{print $2}')
        print_debug "Already logged in to Docker Hub as: $USERNAME"
    fi
fi

# Build the Docker image
print_info "Building Docker image..."

if [ "$MULTI_ARCH" = true ]; then
    # Multi-arch build - must push directly, cannot load locally
    # Build tags for both version and latest
    if [ "$TAG" != "latest" ]; then
        LATEST_IMAGE="${REPO}:latest"
        print_info "Building and pushing multi-arch images: $IMAGE_NAME and $LATEST_IMAGE"
        BUILD_CMD="docker buildx build $NO_CACHE --platform linux/amd64,linux/arm64 --push -t $IMAGE_NAME -t $LATEST_IMAGE $SCRIPT_DIR"
        print_debug "Executing: $BUILD_CMD"
        if docker buildx build $NO_CACHE \
            --platform linux/amd64,linux/arm64 \
            --push \
            -t "$IMAGE_NAME" \
            -t "$LATEST_IMAGE" \
            "$SCRIPT_DIR"; then
            print_success "Multi-arch images built and pushed successfully!"
            print_success "  - $IMAGE_NAME (amd64, arm64)"
            print_success "  - $LATEST_IMAGE (amd64, arm64)"
        else
            print_error "Multi-arch build failed!"
            exit 1
        fi
    else
        print_info "Building and pushing multi-arch image: $IMAGE_NAME"
        BUILD_CMD="docker buildx build $NO_CACHE --platform linux/amd64,linux/arm64 --push -t $IMAGE_NAME $SCRIPT_DIR"
        print_debug "Executing: $BUILD_CMD"
        if docker buildx build $NO_CACHE \
            --platform linux/amd64,linux/arm64 \
            --push \
            -t "$IMAGE_NAME" \
            "$SCRIPT_DIR"; then
            print_success "Multi-arch image built and pushed successfully: $IMAGE_NAME (amd64, arm64)"
        else
            print_error "Multi-arch build failed!"
            exit 1
        fi
    fi
    # For multi-arch, we've already pushed, so skip the push section later
    PUSH=false
    print_debug "Multi-arch build complete, skipping separate push step"
else
    # Single platform build - load locally
    BUILD_CMD="docker buildx build $NO_CACHE --load -t $IMAGE_NAME $SCRIPT_DIR"
    print_debug "Executing: $BUILD_CMD"
    if docker buildx build $NO_CACHE --load -t "$IMAGE_NAME" "$SCRIPT_DIR"; then
        print_success "Docker image built successfully: $IMAGE_NAME"
        print_debug "Image loaded into local Docker daemon"
    else
        print_error "Docker build failed!"
        exit 1
    fi

    # Also tag as latest if a version tag was specified
    if [ "$TAG" != "latest" ]; then
        LATEST_IMAGE="${REPO}:latest"
        print_info "Tagging image as latest: $LATEST_IMAGE"
        print_debug "Executing: docker tag $IMAGE_NAME $LATEST_IMAGE"
        docker tag "$IMAGE_NAME" "$LATEST_IMAGE"
        print_success "Tagged as $LATEST_IMAGE"
    fi
fi

# Push to Docker Hub if requested (single-arch only, multi-arch already pushed)
if [ "$PUSH" = true ]; then
    print_info "Pushing image to Docker Hub..."

    # Push the tagged image
    print_debug "Executing: docker push $IMAGE_NAME"
    if docker push "$IMAGE_NAME"; then
        print_success "Pushed $IMAGE_NAME to Docker Hub"
    else
        print_error "Failed to push $IMAGE_NAME"
        exit 1
    fi

    # Also push latest tag if applicable
    if [ "$TAG" != "latest" ]; then
        LATEST_IMAGE="${REPO}:latest"
        print_debug "Executing: docker push $LATEST_IMAGE"
        if docker push "$LATEST_IMAGE"; then
            print_success "Pushed $LATEST_IMAGE to Docker Hub"
        else
            print_error "Failed to push $LATEST_IMAGE"
            exit 1
        fi
    fi

    print_success "All images pushed successfully!"
else
    print_debug "Push flag not set, skipping push to Docker Hub"
    print_info "Skipping push to Docker Hub (use -p or --push to enable)"
    print_info "To push manually, run:"
    print_info "  docker push $IMAGE_NAME"
    if [ "$TAG" != "latest" ]; then
        print_info "  docker push ${REPO}:latest"
    fi
fi

print_success "Done!"
print_debug "Script completed successfully"
