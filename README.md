# draft-ietf-sidrops-rpki-rsc

## Artifacts

The `artifacts` branch provides in-tree storage for built artifacts.

Each commit in the `artifacts` branch should have exactly two parents:

- The previous head of the `artifacts` branch; and
- The commit containing the source tree from which the artifacts were built.

Thus, the commit containing the artifacts built from a given commit can be
identified by identifying a commit object that is:

- A direct child of the source commit; and
- An ancestor of the head of the `artifacts` branch
