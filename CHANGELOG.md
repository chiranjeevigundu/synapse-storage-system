# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- `src/requirements.txt` containing foundational libraries (`pydantic`, `loguru`, `watchdog`).
- `src/models.py` defining `FileMetadata` Pydantic model for single-source-of-truth metadata.
- `src/utils.py` containing `calculate_sha256` (buffered hashing) and `generate_universe_path` (naming standardization).
- `src/main.py` as an entry point functioning as a dry-run scanner for `/mnt/nas_data/00_INGEST/`, complete with duplicate hash detection and logging.

### Changed
- `src/main.py` updated to run as a 24/7 background service utilizing `watchdog` to monitor the `00_INGEST/` directory in real-time.
- Implemented a persistent `src/ledger.json` for SHA-256 hash duplication checking across reboots.
- Integrated a custom `IngestHandler` to parse the specific "Source Device" from filenames, dynamically update the ledger, and gracefully handle shutdowns.

### Containerization
- `Dockerfile` introduced to package the service using `python:3.11-slim`.
- `docker-compose.yml` created to orchestrate deployment, linking the host's `/mnt/nas_data` to the container and enforcing a `unless-stopped` restart policy.
- `deploy/setup_env.sh` generated to automate the creation of the target NAS folders and assign Docker-friendly permissions.

### Gateway & API Implementation
- **FastAPI Endpoint:** Created `src/ingest_api.py` with an `/upload` route that securely accepts and streams files into the `00_INGEST/` landing zone using multipart forms.
- **API Key Security:** Implemented `X-Api-Key` header authentication to strictly control ingest access.
- **Kong API Gateway:** Configured Kong (`3.11`) in DB-less mode within `docker-compose.yml`, acting as the single front-end proxy on ports 80/443.
- **Declarative Routing:** Generated `config/kong.yml` defining the `ingest-service` and `/ingest` routes, supplemented by enterprise Key-Auth configuration.

### Client-Side Automation
- **Windows Sentinel Agent:** Developed `client/windows_sentinel.ps1` to act as a lightweight, automated intake agent for Windows machines. It monitors a local `NAS_Outbox` folder and uses REST APIs to POST files directly to the Universe.
- **Dynamic Identification:** Integrated `$env:COMPUTERNAME` to automatically label the `source_device` metadata.
- **Client Documentation:** Added `client/README_CLIENT.md` with detailed instructions on establishing the Sentinel as a persistent, hidden Scheduled Task running with highest privileges.

### Mobile Integration
- **iOS/iPadOS Blueprint:** Added `docs/MOBILE_INTEGRATION.md` detailing the exact Apple Shortcut configuration required to bridge mobile devices to the Kong Gateway natively from the iOS Share Sheet.
- **Future Architecture:** Documented Phase 2 proposals involving localized AI Vision Tagging for zero-touch semantic folder routing.

### AI Curation Enhancements
- **VisionClassifier (`src/vision.py`):** Integrated Generative AI to act as the "Curator's Eyes," interpreting raw images and mapping them contextually to the `UNIVERSE_SCHEMA.md` taxonomy.
- **Smart Handler (`src/main.py`):** Updated `IngestHandler` to detect `.jpg`, `.png`, and `.heic` files, automatically triggering AI tagging when standard metadata rules cannot resolve the destination.

### Observability & Dashboarding
- **Metrics Instrumentation:** Integrated `prometheus_client` across `src/main.py` and `src/ingest_api.py` to continuously export operational metrics (`total_files_ingested`, `files_by_source_device`, `ai_categorization_count`, and `nas_storage_usage_percent`).
- **Observability Stack:** Expanded `docker-compose.yml` with `prometheus` and `grafana` containers to visualize homelab operations in real-time.
- **Monitoring Skill:** Created `.antigravity/skills/monitoring.md` to instruct agents on extracting metrics via PromQL to dynamically compile Weekly Reliability Reports.

### Human-in-the-Loop (HITL) Review System
- **CLI Utility (`src/review_tool.py`):** Built a review tool that parses the `ledger.json` to visualize the last 20 automated file decisions. Included a `--reclassify` engine to dynamically move files across NAS volumes and repair the ledger simultaneously.
- **API Extension:** Expanded `src/ingest_api.py` with a `/review` GET endpoint to export recent ledger decisions for future Grafana integrations.
- **Correction Protocol:** Established `.antigravity/skills/correction_protocol.md` empowering agents to automatically execute the reclassification logic whenever a user flags an AI tagging error.
- **Ledger Upgrade:** Refactored `src/main.py`'s `Ledger` class to store rich metadata objects (names, paths, dates) rather than isolated strings, maintaining backward compatibility for legacy hashes.

### Configuration Management & Secrets Hardening
- **Centralized Configuration:** Integrated `pydantic-settings` to govern the repository's critical paths, API keys, and server parameters via a central `src/config.py` module.
- **Environment Virtualization:** Stripped hardcoded secrets from `main.py`, `ingest_api.py`, `vision.py`, and `docker-compose.yml`, migrating them securely to a local `.env` deployment pattern.
- **Template Provided:** Added a `.env.example` file to document the required schema for subsequent server setups.

### Automated Quality Assurance (QA) & Testing
- **Test Suite Initialization:** Integrated `pytest` and `httpx` to establish a formal QA pipeline for the curation logic.
- **Unit Tests:** Authored `tests/test_utils.py` to cryptographically verify the SHA-256 hashing and validate the deterministic UNIVERSE path generation.
- **API Tests:** Added `tests/test_api.py` utilizing the FastAPI TestClient to enforce API Key security protocols and simulate end-to-end file ingestions into the `00_INGEST` layer.
- **CI/CD Scripting:** Provided `scripts/run_tests.sh` to safely spin up a temporary virtualization environment, execute the suite, and automatically clean up test data artifacts.

### The Sentinel Auditor - Version 1.0 Completion
- **Data Integrity Engine (`src/auditor.py`):** Engineered the `IntegrityAuditor` class to traverse the Universe and cryptographically verify all existing files against the immutable ledger to prevent Bit-Rot.
- **Automated Scheduling:** Upgraded `src/main.py` with a background `schedule` thread that autonomously triggers a full systemic health check every Sunday at 02:00 AM.
- **Disaster Recovery Skill:** Added `.antigravity/skills/maintenance.md` to establish the formal protocol for interpreting Corruption Reports and orchestrating "Restore from Backup" procedures.
