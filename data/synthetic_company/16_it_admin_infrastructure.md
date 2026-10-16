---
id: NEX-ADM-001
title: Global IT Infrastructure, Root Certificate Rotation, and Disaster Recovery Runbooks
category: IT Administration
author: Tariq Mansoor (Chief Information Security Officer)
last_updated: 2026-03-02T19:00:00Z
version: 1.1
access_classification: admin
---

# Global IT Administration & Root Key Governance

> **NOTICE: SYNTHETIC DATASET**
> *This document is part of a synthetic, fictional dataset created for Nexora Technologies. All names, projects, policies, metrics, and details are purely fictional.*

*Classification: Administrator Eyes Only — Tier 0 Infrastructure Clearance*

## Root Authority & PKI Management
- **Vault Root CA**: Nexora internal certificates are generated from an air-gapped HashiCorp Vault cluster located in AWS us-east-1 and backed by an AWS CloudHSM cluster.
- **Root Key Ceremony**: Conducted annually in November. Requires dual-custody authorization from the CISO and Lead Infrastructure Architect using physical m-of-n YubiHSM split keys.

## Break-Glass Emergency Procedures
- In a catastrophic outage where Okta SSO and AWS Identity Center are unreachable, administrators may invoke the "Break-Glass" IAM role `arn:aws:iam::123456789012:role/NexoraBreakGlassAdmin`.
- Access triggers immediate high-priority SMS alerts to the executive team and commences automated AWS CloudTrail immutability logging.

## Disaster Recovery Objectives
- **RPO (Recovery Point Objective)**: < 5 minutes for Cortex-V and PostgreSQL transactional databases via cross-region asynchronous WAL replication to us-west-2.
- **RTO (Recovery Time Objective)**: < 30 minutes for complete service mesh DNS failover to the secondary recovery region.
