#!/bin/bash
# Exit on error
set -o errexit

# Install python dependencies
pip install -r requirements.txt

# Create any necessary database tables or run migrations
# python ./database/execute_schema.py
