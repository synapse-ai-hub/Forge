"""Workflows end-to-end tests for synapseForge.

Verifies the deterministic workflow lifecycle against a live backend:
validation, save, selection and real runner execution. Follows the same
declarative YAML methodology as ``tests.e2e.runner``: no mocks, real endpoints,
asserting on contract structure and persisted values.

Usage::

    python -m tests.workflows.runner                       # all scenarios
    python -m tests.workflows.runner --only workflow-save  # single scenario
    python -m tests.workflows.runner --base-url http://127.0.0.1:8000

Prerequisites: the backend must be running.
"""
