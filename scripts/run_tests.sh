#!/bin/bash

echo "========================================="
echo "Universe HITL - Automated Test Runner"
echo "========================================="

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Set the Python path so tests can discover src modules
export PYTHONPATH=$(pwd)/src

# Set a dummy NAS base path for testing so we don't mess up real data
export NAS_BASE_PATH=$(pwd)/test_nas_data
export API_KEY=test_runner_secret

# Ensure the scripts are executable
chmod +x scripts/run_tests.sh

# Run pytest
echo "Running pytest suite..."
python -m pytest tests/ -v

TEST_EXIT_CODE=$?

# Cleanup temporary test environment
if [ -d "test_nas_data" ]; then
    echo "Cleaning up temporary test environment..."
    rm -rf test_nas_data
fi

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed successfully!"
else
    echo "❌ Tests failed. Please check the logs above."
fi

exit $TEST_EXIT_CODE
