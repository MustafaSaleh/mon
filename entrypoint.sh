#!/bin/bash

# Function to start the application
start_app() {
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
}

# Main loop for self-healing
while true; do
    start_app
    
    # If the app crashes, wait 5 seconds before restarting
    echo "Application crashed or stopped. Restarting in 5 seconds..."
    sleep 5
done