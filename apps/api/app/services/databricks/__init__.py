"""Databricks source module — extraction, analysis, and doc generation pipeline.

Key entry points:
  - extraction_orchestrator.run_extraction() — discover + export + extract SQL
  - analysis_orchestrator.run_analysis()     — fingerprint + counters + clusters
  - doc_orchestrator.run_generation()        — build payloads + LLM author + validate
"""
