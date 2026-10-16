---
id: NEX-SUP-001
title: Customer Support Procedures, Severity Matrix, and SLA Escalations
category: Customer Support
author: Liam O'Connor (Director of Global Customer Engineering)
last_updated: 2026-02-12T15:20:00Z
version: 1.8
access_classification: employee
---

# Customer Support Procedures & SLA Escalation

> **NOTICE: SYNTHETIC DATASET**
> *This document is part of a synthetic, fictional dataset created for Nexora Technologies. All names, projects, policies, metrics, and details are purely fictional.*

This document establishes standard operating procedures for the Nexora Global Technical Support and Customer Engineering teams.

## Severity Level Definitions
- **Severity 1 (Critical / Blocker)**: Complete production outage, data corruption, or total failure of the telemetry ingestion pipeline affecting >25% of hosts.
  - *Initial Response SLA*: 15 minutes (24/7/365).
  - *Cadence*: Hourly executive status updates via status page and email.
- **Severity 2 (Major / Degraded)**: Significant platform degradation, severe query latency (>10s), or collector crash loops without general outage.
  - *Initial Response SLA*: 1 hour (24/7).
  - *Cadence*: Updates every 4 hours.
- **Severity 3 (Moderate / Minor)**: Non-critical feature bug, UI glitch, or single connector failure with available workaround.
  - *Initial Response SLA*: 4 business hours.
- **Severity 4 (Low / Informational)**: Feature requests, documentation clarification, or general configuration advice.
  - *Initial Response SLA*: 1 business day.

## Escalation Path & Incident Bridge
1. **Tier 1 Support Engineer**: Triages Zendesk ticket, reproduces telemetry payload in staging, verifies license tier.
2. **Tier 2 Technical Support Engineer (TSE)**: Examines cluster logs, inspects eBPF probe crashes, inspects ingestion lag.
3. **Tier 3 / Escalation Engineer**: Pages the on-call Site Reliability Engineer via `#oncall-sre` in Slack or PagerDuty escalation policy `EP-PULSE-CORE`.
4. **Major Incident Commander (MIC)**: For Sev-1 incidents, the MIC establishes a Zoom Incident War Room and directs the communications scribe.
