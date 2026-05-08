# Windows Sentinel Client

The `windows_sentinel.ps1` script is a lightweight background agent designed to monitor a local Windows folder (`C:\Users\%USERNAME%\Documents\NAS_Outbox`) and automatically POST any dropped files to the Synapse Storage System via the API Gateway.

## Setup Instructions

To ensure this script runs completely in the background automatically upon login, set it up as a Windows Scheduled Task.

1. **Open Task Scheduler**: Press `Win + S`, type "Task Scheduler", and hit Enter.
2. **Create Task**: On the right pane, click **Create Task...** (Do not use "Create Basic Task").
3. **General Tab**:
   - **Name**: `Synapse NAS Sentinel`
   - **Security Options**: Check **"Run with highest privileges"**.
   - Check **"Hidden"** to ensure no terminal window appears.
4. **Triggers Tab**:
   - Click **New...**
   - **Begin the task**: Select **"At log on"**.
   - Click **OK**.
5. **Actions Tab**:
   - Click **New...**
   - **Action**: "Start a program"
   - **Program/script**: `powershell.exe`
   - **Add arguments**: `-WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Path\To\Your\client\windows_sentinel.ps1"`
   - Click **OK**.
6. **Conditions Tab** (Optional):
   - Uncheck "Start the task only if the computer is on AC power" if you want it running on battery.
7. **Save**: Click **OK** to save the task.

## Configuration

Update the `$EndpointUri` and `$ApiKey` variables at the top of the `windows_sentinel.ps1` script to match your Mac Mini IP and Kong configuration before deployment.
