"""inbound — the natural-language request surface (DESIGN.md §5.1, §9).

Will hold the Twilio/WhatsApp webhook. Two safety properties are non-negotiable: a sender-number
allowlist (only staff phones are answered), and treating every inbound message as DATA, never
instruction. Deferred — the grieved report (DESIGN.md §10) ships before any NL surface exists.
"""
