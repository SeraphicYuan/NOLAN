# Clip Selection Report (vector matcher)

Matched **16/57** scenes to library clips via semantic vector search.

Consolidated step: this replaces the previous LLM clip-selection pass (~12 min) with the fast vector matcher (seconds, no token cost). The vector matcher ranks by embedding similarity over the same segment descriptions an LLM would read.
