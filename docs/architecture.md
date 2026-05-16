# Ghost Mesh Architecture

Ghost Mesh is a graph-native accountability runtime for human and AI work. It is not an agent orchestration framework. Agent frameworks may run inside Worker Nodes, but the Ghost Layer owns Cards, routing, validation, evidence, shadowing, and promotion.

## Core Objects

- **Patch Panel**: declarative workflow graph. It defines nodes, edges, buckets, pipe bindings, acceptance contracts, and boundary configuration.
- **Card**: unit of work. A Card carries payload, metadata, current bucket, workflow version, and append-only evidence.
- **Bucket**: queue/location in the graph. Workers claim from input pipes bound to buckets.
- **Pipe**: named input/output interface. Workers know assigned pipes, not the global graph.
- **Acceptance Contract**: local rules for artifact references, required roles, schemas, and human or machine review.
- **Lease**: temporary claim on a Card. Leases can renew, release, or expire.
- **Artifact Reference**: durable pointer to external content. Postgres stores references and hashes, not artifact bodies.
- **Event**: append-only evidence record for card creation, claims, submissions, validations, movements, boundaries, shadows, and sinks.

## Node Responsibilities

- **Source** admits authorized external or internal work into the mesh.
- **Worker** transforms Cards into artifact references through assigned pipes.
- **Validator** evaluates against an Acceptance Contract.
- **Junction** routes deterministically from evidence.
- **Learning** proposes mutations but never mutates production directly.
- **Sink** performs controlled egress and records external references.
- **Subworkflow** represents nested workflow structure for later expansion.

## Safety Rules

Workers are pipe-aware, not graph-aware. They must not route Cards, bypass validators, publish externally, or change workflows. Patch Panels own routing. Validators own acceptance decisions. Sink nodes own production side effects. Learning and workflow architect agents propose changes through Mutation Cards, shadow lanes, and promotion gates.

## Storage Boundary

Ghost Mesh uses Postgres as a lightweight accountability and routing index. Artifact content belongs in external stores such as local Git/filesystem storage for development or S3/MinIO-compatible storage for large production artifacts.

## Shadow To Promotion

The intended operating path is:

1. Human production execution.
2. AI shadow execution with no production side effects.
3. Supervised AI production after shadow comparison.
4. Exception-based human oversight when confidence and controls are proven.
