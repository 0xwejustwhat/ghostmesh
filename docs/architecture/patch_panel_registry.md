# Patch Panel Registry Architecture

The Patch Panel registry indexes governed workflow definitions for discovery and launch.
It does not own proposal lifecycle state.

Registry entries track:

- Patch Panel id and version
- discovery metadata
- owner and required permissions
- lifecycle status such as draft, review, published, archived, or superseded
- provenance metadata supplied by authorized publication paths

Registry publication for generated Patch Panels must come from the
`system_pp_approval` registry publication sink. Indexing code validates that publication
requests are backed by Card history showing topology validation, governance routing, and
sink execution evidence.

Direct registry APIs remain for explicitly authorized registry maintenance, but workflow
proposal validation, approval, rejection, and publication are graph-native Card flows.
