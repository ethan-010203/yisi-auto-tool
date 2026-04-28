# Backend Development Guidelines

> Backend contracts and operational patterns for this project.

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Runtime Queue](./runtime-queue.md) | SQLite queue, worker concurrency, runtime limits | Active |

## Pre-Development Checklist

- Read [Runtime Queue](./runtime-queue.md) before changing task execution, worker loops, queue claiming, cancellation, or runtime limits.

## Quality Check

- Run `py -3 -m py_compile` on changed Python backend files.
- For queue changes, validate `claim_next_execution` behavior with at least one cross-department concurrency case.
