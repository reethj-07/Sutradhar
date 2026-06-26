"""Evaluation framework (PRD §11, Hero Feature #3).

Synthetic-caller simulation, ASR-noise / adversarial injection, LLM-as-judge
scoring, per-turn latency capture and a CI regression suite. Fully built in M4;
this package is its home. (The directory name matches PRD §16 even though it
shadows the builtin ``eval`` — modules are run as ``python -m eval.run``.)
"""
