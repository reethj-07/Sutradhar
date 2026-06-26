"""Transport implementations behind one interface (PRD §6.3):

* ``websocket`` — default browser client transport (M1).
* ``webrtc`` — optional aiortc path (M5, behind the same interface).
* ``telephony`` — simulated telephony: 8 kHz, SIP-like lifecycle, no carrier (M5).
"""
