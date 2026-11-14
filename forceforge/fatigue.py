"""Load-spectrum fatigue screening using user-supplied S-N curve parameters.

This is NOT an endurance-limit certification, weld detail category check,
fracture mechanics model, or a substitute for physical fatigue qualification.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SNModel:
    reference_amplitude_pa: float  # must be material/geometry/joint specific
    reference_cycles: float
    slope_m: float
    ultimate_strength_pa: float

    def __post_init__(self):
        if min(self.reference_amplitude_pa,self.reference_cycles,self.slope_m,
               self.ultimate_strength_pa) <= 0:
            raise ValueError('S-N parameters must all be positive')


@dataclass(frozen=True)
class StressBlock:
    amplitude_pa: float
    mean_pa: float
    cycles: float


def miner_damage(sn: SNModel, spectrum: list[StressBlock]) -> dict:
    """Goodman tension-mean correction + power S-N + linear Palmgren-Miner D.

    For mean stress >= ultimate, no finite fatigue cycle count is supported.
    Compressive mean stress gets no credit: conservative screening assumption.
    """
    if not spectrum:
        raise ValueError('Need at least one stress block')
    lines=[]
    damage=0.0
    for block in spectrum:
        if block.amplitude_pa < 0 or block.cycles < 0:
            raise ValueError('Stress amplitude and cycles must be nonnegative')
        if block.mean_pa>=sn.ultimate_strength_pa:
            n_failure=0.0
            d=math.inf if block.cycles>0 else 0.0
            corrected=math.inf
        elif block.amplitude_pa==0:
            n_failure=math.inf
            d=0.0
            corrected=0.0
        else:
            corrected = block.amplitude_pa/(1-max(block.mean_pa,0.0)/sn.ultimate_strength_pa)
            n_failure=sn.reference_cycles*(sn.reference_amplitude_pa/corrected)**sn.slope_m
            d=block.cycles/n_failure
        damage+=d
        lines.append({'amplitude_pa':block.amplitude_pa,'mean_pa':block.mean_pa,
            'cycles':block.cycles,'goodman_amplitude_pa':corrected,
            'estimated_cycles_to_failure':n_failure,'damage':d})
    return {'miner_damage':damage,'damage_limit_utilization':damage,
        'passes_unit_damage_screen':damage<1.0,
        'repetitions_until_unit_damage':(1.0/damage if damage>0 else math.inf),
        'blocks':lines}
