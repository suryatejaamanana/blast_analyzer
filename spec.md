
# 📄 spec.md

# Impact Trace – Blast Radius Analysis System

## 1. Project Overview

### 1.1 Background

In real-world software systems, even a small change can have wide-reaching consequences.

Adding a field to an API, modifying validation logic, or refactoring a shared function may silently impact:

* Downstream services
* Data flows
* Business logic
* Existing tests and assumptions

Currently, engineers rely on manual inspection, experience, and tribal knowledge to estimate the blast radius of a change. This approach is error-prone and non-scalable.

### 1.2 Problem Statement

Build a system that:

Given:

1. An existing codebase (single programming language), and
2. A clearly specified code change (API change, behavior change, structural change)

Can automatically determine the **blast radius** of that change in a structured, explainable way.

The system must answer:

> “If I make this change, what parts of the system are impacted — and why?”

---

## 2. Goals and Objectives

### 2.1 Primary Goals

* Model a codebase structurally and semantically
* Accept structured change intent
* Analyze direct and indirect impacts
* Generate an explainable blast radius report

### 2.2 Non-Goals

* No UI required
* No CI/CD integration
* No multi-language support
* No runtime monitoring system

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
Codebase → Parser → Graph Model → Change Intent Engine → Impact Analyzer → Report Generator
```

---

## 4. Core Functional Requirements

## 4.1 Codebase Modeling

### 4.1.1 Parsing

The system shall:

* Parse source files
* Extract structural elements:

  * Modules
  * Classes
  * Functions
  * APIs

### 4.1.2 Relationship Detection

The system shall detect:

* Function calls
* Imports and dependencies
* Class inheritance
* API usage
* Data flow relationships

### 4.1.3 Graph Representation

The codebase shall be represented as a directed graph:

#### Nodes:

* Module
* Class
* Function
* API
* Data entity

#### Edges:

* CALLS
* IMPORTS
* DEPENDS_ON
* RETURNS
* READS
* WRITES

This graph represents the **current reality** of the system.

---

## 5. Change Intent Module

### 5.1 Structured Change Input

The system shall accept structured change descriptions such as:

```json
{
  "change_type": "api_modification",
  "target": "UserAPI.getProfile",
  "modification": "add_optional_field",
  "field_name": "middleName"
}
```

Supported change types:

* API modification
* Function logic change
* Validation rule change
* Refactor shared method
* Data model change

### 5.2 Change Intent Validation

The system shall:

* Verify target existence in graph
* Validate change type applicability
* Normalize change into internal representation

---

## 6. Blast Radius Analysis

### 6.1 Direct Impact Detection

Direct impacts include:

* Immediate callers
* Immediate dependencies
* Contract boundaries

### 6.2 Indirect Impact Detection

Indirect impacts include:

* Downstream call chains
* Transitive dependencies
* Data propagation effects

Graph traversal techniques:

* BFS / DFS
* Dependency propagation rules

---

## 7. Impact Classification

Each impacted component shall be classified as:

| Category               | Description                        |
| ---------------------- | ---------------------------------- |
| API-Level              | Interface or contract impact       |
| Business Logic         | Core computation or decision logic |
| Data Handling          | Data structure or schema change    |
| Contract Compatibility | Potential breaking change          |
| Test Impact            | Affected unit/integration tests    |

---

## 8. Impact Severity Levels (Bonus Feature)

| Severity | Meaning                                |
| -------- | -------------------------------------- |
| Low      | Internal refactor, no interface impact |
| Medium   | Affects dependent modules              |
| High     | Potential contract-breaking change     |

Severity factors:

* Number of downstream nodes
* External exposure (public API)
* Data model modification
* Validation rule changes

---

## 9. Explainability Requirements

Every impacted node must include:

* Why it is impacted
* Path from change to impacted node
* Type of dependency

Example explanation:

```
Function: OrderService.createOrder
Impact Type: Indirect
Reason:
UserAPI.getProfile → UserService.fetchUser → OrderService.createOrder
Change in API response structure may affect user object mapping.
```

---

## 10. Output Format

The blast radius report must be:

* Structured
* Engineer-readable
* Explainable

### 10.1 Markdown Output Example

```markdown
# Blast Radius Report

## Change Summary
API Modified: UserAPI.getProfile
Modification: Added optional field 'middleName'

## Direct Impacts
- UserService.fetchUser
- ProfileMapper.mapToDTO

## Indirect Impacts
- OrderService.createOrder
- NotificationService.sendWelcomeEmail

## Risk Zones
- External API contract exposure
- Unknown test coverage in ProfileMapper

## Severity: Medium
```

### 10.2 JSON Output Example

```json
{
  "change": "...",
  "direct_impacts": [],
  "indirect_impacts": [],
  "risk_areas": [],
  "severity": "medium"
}
```

---

## 11. Graph Design Principles

The graph model must be:

* Minimal (no redundant nodes)
* Accurate (true structural representation)
* Deterministic (same code → same graph)
* Queryable (efficient traversal)

Possible implementation:

* NetworkX
* Custom adjacency list
* Neo4j (optional)

---

## 12. Traceability

The system must support:

Change Intent → Target Node → Traversal Path → Impacted Nodes

Trace must be visible in report.

---

## 13. Risk and Uncertainty Detection

The system shall highlight:

* Reflection usage
* Dynamic imports
* Runtime dependency injection
* Unresolved symbols

These areas should be marked as:

```
Unknown Impact Zone
```

---

## 14. Evaluation Criteria Alignment

| Criteria       | Implementation Mapping      |
| -------------- | --------------------------- |
| Accuracy       | Graph-based traversal       |
| Completeness   | Direct + Indirect analysis  |
| Explainability | Explicit path reporting     |
| Graph Design   | Minimal node-edge structure |

---

## 15. Assumptions

* Single programming language
* Static analysis only
* Codebase compiles
* Change intent is structured and explicit

---

## 16. Constraints

* No UI
* No runtime instrumentation
* No multi-language parsing

---

## 17. Future Enhancements

* Visual graph rendering
* IDE plugin integration
* CI pre-merge blast radius report
* Historical change comparison
* Impact simulation

---

## 18. Expected Outcome

The system makes blast radius explicit before code is merged.

It does not predict runtime failures.

It increases engineer confidence by making impact visible.

---

# End of spec.md

If you want, I can also generate:

* ✅ architecture.md
* ✅ design.md
* ✅ implementation plan
* ✅ Graph schema definition
* ✅ Sample Python project prototype
* ✅ Full documentation (20–30 pages structured report)



