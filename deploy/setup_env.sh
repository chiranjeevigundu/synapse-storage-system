#!/bin/bash
# Setup script to initialize NAS structure and set permissions for Docker

echo "Initializing Synapse Storage System Environment..."

# Create the INGEST directory
mkdir -p /mnt/nas_data/00_INGEST

# Note: Additional directories from UNIVERSE_SCHEMA.md could be created here.

# Set the correct permissions for the Docker user. 
# This assumes the Docker host user or PUID is 1000, adjust as necessary for the Mac Mini host.
chown -R 1000:1000 /mnt/nas_data
chmod -R 775 /mnt/nas_data

echo "Environment setup complete."
