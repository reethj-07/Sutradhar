"""Mock CRM backend for the demo vertical (PRD §10, §16).

A FastAPI + SQLite service exposing the tools the agent calls during outbound
lead qualification: ``lookup_customer``, ``book_slot``, ``get_order_status``,
``update_disposition``. Fully implemented in M3; this package is the home for it.
"""
