#!/bin/bash
# Install Short Script Factory services via launchctl
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LAUNCHAGENTS="$HOME/Library/LaunchAgents"

echo "Installing Short Script Factory services..."

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$LAUNCHAGENTS"

cp "$SCRIPT_DIR/com.tpe.script-worker.plist" "$LAUNCHAGENTS/"
cp "$SCRIPT_DIR/com.tpe.script-api.plist" "$LAUNCHAGENTS/"

launchctl load "$LAUNCHAGENTS/com.tpe.script-worker.plist"
launchctl load "$LAUNCHAGENTS/com.tpe.script-api.plist"

echo "Services installed:"
echo "  Worker:  com.tpe.script-worker  (health: http://localhost:5176)"
echo "  API:     com.tpe.script-api     (http://localhost:5175)"
echo "Logs: $PROJECT_DIR/logs/"
echo ""
echo "To uninstall:"
echo "  launchctl unload $LAUNCHAGENTS/com.tpe.script-worker.plist"
echo "  launchctl unload $LAUNCHAGENTS/com.tpe.script-api.plist"
