# Mobile Integration (iOS/iPadOS) Blueprint

This document defines the configuration for the Apple Shortcut that acts as the mobile bridge between your iPhone/iPad and the Synapse Storage System via the Kong Gateway.

## Apple Shortcut Workflow

Create a new Shortcut and configure the following sequential actions:

### 1. Input Handling
- Enable the **Show in Share Sheet** option in the Shortcut details.
- Configure the Share Sheet to accept **Files** and **Photos** as the primary input types.
- The workflow begins by receiving this `[Shortcut Input]`.

### 2. Device Identity
- Add a **Dictionary** action.
- Add a key `source_device` with the text value corresponding to your specific device (e.g., `iPhone_17_Pro` or `iPad_M4`). This ensures the API accurately attributes the metadata and prefixes the filename.

### 3. Intelligent Routing (Optional)
- Add a **Choose from Menu** action to prompt for the target category, mapping directly to your `UNIVERSE_SCHEMA.md`:
  - `Professional` -> `01_PROFESSIONAL/Deployments`
  - `Technical` -> `02_TECHNICAL_HOMELAB/Hardware_Configs`
  - `Personal` -> `03_PERSONAL/Mobile_Backups`
  - `Financial` -> `04_FINANCIAL/Invoices_Receipts`
- Assign the chosen destination to a `TargetCategory` variable.

### 4. Network Request
- Add a **Get Contents of URL** action.
- **URL**: `https://[Gateway-URL]/ingest` *(Ensure you use your Tailscale IP or local IP)*.
- **Method**: `POST`
- **Headers**:
  - `x-api-key`: `[Your_API_Key]`
- **Request Body**: Set to `Form`. Map the fields to your API schema:
  - `file`: `[Shortcut Input]` (Type: File)
  - `source_device`: `[Dictionary Value -> source_device]` (Type: Text)
  - `category`: `[TargetCategory Variable]` (Type: Text)

### 5. Success Feedback
- Immediately following the URL request, add an `If` statement to verify a 200 OK status.
- Add a **Vibrate Device** action to provide tactile confirmation.
- Add a **Show Notification** action with a success message (e.g., *"Upload to Universe Complete!"*).

---

## Phase 2: AI Vision Tagging (Future Iteration)

In a future architectural iteration, the mobile bridge will bypass the manual menu routing and incorporate **AI Vision Tagging**. 

The Shortcut will initially send photos to a localized, lightweight Vision-capable AI agent on the Mac Mini. This agent will analyze the visual context (e.g., recognizing a tax W2 form versus a hardware rack) and automatically compute the ideal `category` mapping within the UNIVERSE structure, completely automating the triage and ingestion phase.
