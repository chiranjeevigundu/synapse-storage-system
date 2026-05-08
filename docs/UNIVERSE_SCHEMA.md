# UNIVERSE SCHEMA

This document serves as the master map for the automated curation logic. It outlines the enterprise-grade taxonomy for all files managed on the UGREEN NAS.

## Directory Structure

The following top-level directory structure is strictly maintained:

- **`00_INGEST/`**: The landing zone for all incoming files from laptops and mobile devices before they are processed.
- **`01_PROFESSIONAL/`**
  - `Projects/`
  - `Research/`
  - `Deployments/`
  - `Documentation/`
- **`02_TECHNICAL_HOMELAB/`**
  - `Network_Architecture/`
  - `Hardware_Configs/`
  - `Docker_Stacks/`
  - `MCP_Source_Code/`
- **`03_PERSONAL/`**
  - `Mobile_Backups/` *(categorized by device)*
  - `Media_Archives/`
  - `Archives/`
- **`04_FINANCIAL/`**
  - `Tax_Records/`
  - `Invoices_Receipts/`
  - `Legal_Documents/`
- **`05_SYSTEM/`**
  - Backups of the Mac Mini Ubuntu host.
  - NAS configuration exports.

## Naming Convention Standard

All curated files must adhere to the following strict naming conventions:

1. **Format:** `YYYY-MM-DD_SourceDevice_OriginalName`
2. **Whitespace:** All spaces must be replaced with underscores (`_`).

## Duplication Prevention & Verification

Before moving any file from `00_INGEST/` to its final curated destination, the **Curator agent must**:
- Calculate the file's hash.
- Verify this hash against a local ledger maintained within `00_INGEST/` to guarantee duplication prevention.
