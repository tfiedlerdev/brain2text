import torch
from typing import NamedTuple, Optional


class SampleBatch(NamedTuple):
    input: torch.Tensor
    target: Optional[
        torch.Tensor
    ]  # Batch of tokenized targets (i.e. a batch of lists of target ids)

    def cuda(self):
        copy = self._replace(
            input=self.input.cuda(),
            target=self.target.cuda() if self.target != None else None,
        )
        # Putting all tensors of subclass attributes to cuda
        for key, value in self.__dict__.items():
            if isinstance(value, torch.Tensor):
                copy.__setattr__(key, value.cuda())
            else:
                copy.__setattr__(key, value)
        return copy

    def copy_and_change(self, **diff):
        copy = self._replace(**diff)
        for key, value in self.__dict__.items():
            copy.__setattr__(key, value)

        return copy


class B2tSampleBatch(SampleBatch):
    day_idxs: torch.Tensor
    input_lens: torch.Tensor
    target_lens: Optional[torch.Tensor]


class PhonemeSampleBatch(B2tSampleBatch):
    transcriptions: Optional[list[str]]
    phonemes: list[list[str]]
