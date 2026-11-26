"""Hub onboarding services (ADR 0012, 0013; Spec 00 §3 Onboarding, Data package).

Only used when ``DEPLOYMENT_MODE=hub``; the tables exist only in a hub database (migration
0011). Modules:

* :mod:`.common`: constants, processing records, onboarding status and its transitions;
* :mod:`.sources`: raw source registry (files in the hub storage directory);
* :mod:`.base`: the automated base step of onboarding (clip, assign stable ids, checks);
* :mod:`.facilities`: facility import template, validation, changesets and history;
* :mod:`.coverage`: the coverage matrix (municipality × layer);
* :mod:`.publish`: study areas, package assembly, propagation of updates.
"""
