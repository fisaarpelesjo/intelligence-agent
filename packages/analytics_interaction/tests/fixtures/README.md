# Fixture set — T147

**TEST-ONLY. A fixture is never evidence for an external record.**

Four directories, one per boundary this feature refuses to cross in production:

| Directory | Stands in for | The production state it replaces |
|---|---|---|
| `catalog/` | `001`'s published catalog and freshness snapshot | a real release, which `D-1`/`D-8` leave unpublishable |
| `governance/` | approved-shaped `D-18` and `D-19` content | `interpretation_governance/`, which holds no approved instance |
| `seal/` | a synthetic `D-21` key and a stand-in sealing provider | no key exists anywhere in this repository |
| `execution/` | a fake `ExecutionPort` | `002`'s entry point against a warehouse, which `D-12` gates |

## Why these exist at all

Every one of the four external records these stand in for is **open**, so the
production path refuses. A suite with no fixtures could only ever assert the
refusals — and a feature whose success path has never run is a feature nobody
has tested.

So the fixtures exercise the success path that production refuses, and they are
marked at every level so nobody can mistake the two:

* each module says `TEST-ONLY` in its docstring;
* every synthetic value carries a `fixture-only-...` marker in its own text;
* `test_fixture_containment.py` asserts **no `src/` module** references any of
  them, and that no flag, environment variable or mode selects one.

## What a fixture is never

Not readiness evidence. Not an approval. Not a proposal for what the governed
value should be. Not a reason to mark an external record ready.

The synthetic `D-18` formulas exist so the arithmetic can be exercised; they are
not suggested formulas. The synthetic `D-21` key exists so sealing can be
exercised; it is not provisioned key material. The distinction matters most
precisely when a suite is green, because that is when somebody is most tempted
to read it as done.
