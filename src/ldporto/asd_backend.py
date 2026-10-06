"""Optional Active Speaker Detection backend contract.

The built-in v4 path remains heuristic/consensus. External neural ASD adapters must
implement this contract and prove a measured improvement before becoming a default.
"""
from abc import ABC, abstractmethod


class ASDBackend(ABC):
    name = 'abstract'
    calibrated_probability = False

    @abstractmethod
    def capabilities(self):
        """Return runtime/license/model requirements without loading heavy weights."""
        raise NotImplementedError

    @abstractmethod
    def infer(self, *, video, audio, intervals, observations, config):
        """Return evidence rows aligned to real timestamps; must not invent person IDs."""
        raise NotImplementedError


class HeuristicConsensusBackend(ASDBackend):
    name = 'heuristic_consensus'

    def capabilities(self):
        return {'available': True, 'weights_required': False, 'gpu_required': False,
                'calibrated_probability': False, 'default': True}

    def infer(self, **kwargs):
        raise RuntimeError('Heuristic consensus is executed by active_speaker.py; this adapter is an interface marker, not a second implementation.')


EXTERNAL_CANDIDATES = {
    'lr_asd': {'default': False, 'adapter_implemented': False, 'requires_local_benchmark': True},
    'light_asd': {'default': False, 'adapter_implemented': False, 'requires_local_benchmark': True},
    'talknet': {'default': False, 'adapter_implemented': False, 'requires_local_benchmark': True},
    'c3asd': {'default': False, 'adapter_implemented': False, 'requires_local_benchmark': True},
}


def available_backends():
    return {'heuristic_consensus': HeuristicConsensusBackend().capabilities(), **EXTERNAL_CANDIDATES}
