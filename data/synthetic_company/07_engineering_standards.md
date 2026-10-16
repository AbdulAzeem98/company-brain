---
id: NEX-ENG-001
title: Engineering Standards, Code Review Conventions, and Deployment Guidelines
category: Engineering Standards
author: Devon Chen (Staff Principal Engineer)
last_updated: 2026-02-05T14:00:00Z
version: 3.2
access_classification: employee
---

# Software Engineering Standards

> **NOTICE: SYNTHETIC DATASET**
> *This document is part of a synthetic, fictional dataset created for Nexora Technologies. All names, projects, policies, metrics, and details are purely fictional.*

These standards apply to all software engineers, reliability engineers, and technical contributors across all repositories under the `nexora-tech` GitHub organization.

## Language Standards & Frameworks
- **Primary Backends**: Python 3.12+ (FastAPI, Pydantic v2, Pytest) and Rust (for high-throughput telemetry ingestion daemons PCD).
- **Frontend**: TypeScript, React 19, and Next.js with Tailwind CSS or vanilla CSS design tokens.
- **Database & Persistence**: PostgreSQL 16 for transactional state, ClickHouse/Cortex-V for telemetry time-series, Redis 7.2 for caching and rate limiting.

## Code Review & Pull Request Lifecycle
1. **Branch Naming**: Format must follow `feat/JIRA-123-short-desc` or `fix/JIRA-123-short-desc`.
2. **Reviewers**: Every PR requires a minimum of **two approving reviews**, one of which must be an designated CODEOWNER for the module.
3. **Automated CI Gates**:
   - 100% passing Unit and Integration test suites.
   - Code coverage delta must not decrease (`target >= 85%`).
   - Static analysis: Ruff (linting & formatting for Python), Clippy (Rust), Biome/ESLint (TypeScript).
   - Secret scanning via Gitleaks and Trivy container vulnerability scanning.

## Trunk-Based Development & Deployments
- All features are merged into `main` behind feature flags managed via LaunchDarkly.
- Continuous deployment pipelines automatically trigger staging deployments on every merge.
- Production promotions utilize automated Canary rollouts with 10%, 25%, 50%, and 100% traffic progression monitored by Nexora Pulse.
