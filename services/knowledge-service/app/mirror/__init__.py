"""The glossary→KG mirror: the consumer's own view of what it should be holding.

D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER — the glossary is the SSOT and the KG is its
projection, delivered at-least-once with no reconciliation. Nothing compared the two
stores, so an event lost while a handler was broken stayed lost, silently, forever.
"""
