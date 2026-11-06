"""Deterministic entry-to-effect capability composition.

The composer consumes only the N3 resolved contract. It
uses curated effect categories, a hard traversal budget and resolution floors;
it never calls an LLM and never infers a business label from a directory name.
"""

from __future__ import annotations

from ..errors import BudgetError
from ..resolution.contracts import TraversalBudget
from ..resolution.lifecycle import ResolvedProgram
from .composition_model import MAX_CAPABILITY_SLICES as _MAX_CAPABILITY_SLICES
from .contracts import (
    CapabilityModel,
)
from .input_normalization import collect_inputs as _collect_inputs
from .seed_selection import select_seeds as _select_seeds
from .traversal import compose_seed as _compose_seed


def compose_capabilities(
    resolved: ResolvedProgram,
    *,
    budget: TraversalBudget | None = None,
    max_slices: int = _MAX_CAPABILITY_SLICES,
) -> CapabilityModel:
    """Compose one deterministic capability slice per evidenced public entry."""
    if max_slices < 1:
        raise BudgetError("machine.capability.invalid-slice-budget")
    traversal_budget = budget or TraversalBudget()
    entries, seeds, adjacency, effects, resources, transitions = _collect_inputs(resolved)
    selected = _select_seeds(seeds, entries, max_slices=max_slices)
    slices = tuple(
        _compose_seed(
            seed,
            entries,
            adjacency,
            effects,
            resources,
            transitions,
            traversal_budget,
        )
        for seed in selected
    )
    selected_ids = {seed.entry_id for seed in selected}
    uncovered = tuple(seed.entry_id for seed in seeds if seed.entry_id not in selected_ids)
    inventory = tuple(
        {
            "entryId": seed.entry_id,
            "signature": seed.signature,
            "trigger": dict(seed.trigger),
            "expansionStatus": "expanded" if seed.entry_id in selected_ids else "not-expanded",
            "reasonCode": ""
            if seed.entry_id in selected_ids
            else "machine.capability.slice-budget",
        }
        for seed in seeds
    )
    return CapabilityModel(slices, len(seeds), uncovered, seed_inventory=inventory)


__all__ = ["compose_capabilities"]
