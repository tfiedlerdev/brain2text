import re
from typing import Literal, NamedTuple
import numpy as np
import torch
from src.datasets.batch_types import SampleBatch
from src.util.phoneme_helper import PHONE_DEF_SIL, get_phoneme_seq
from src.datasets.audio_with_phonemes_seq import AudioWPhonemesDatasetArgsModel
from src.datasets.base_dataset import BaseDataset, Sample
import os
import soundfile
from torch.nn.functional import pad
from src.args.yaml_config import YamlConfigModel
from g2p_en import G2p


class TimitA2PSeqSample(NamedTuple):
    phoneme_ids: list[int]  # List of phoneme ids
    transcript: str
    input: torch.Tensor
    phonemes: str  # TODO: remove after debugging


class TimitA2PSeqSampleBatch(SampleBatch):
    transcripts: list[str]
    input_lens: torch.Tensor
    target_lens: torch.Tensor
    phonemes: list[str]  # TODO: remove after debugging


class TimitA2PSeqDataset(BaseDataset):
    def __init__(
        self,
        config: AudioWPhonemesDatasetArgsModel,
        yaml_config: YamlConfigModel,
        split: Literal["train", "val", "test"],
    ):
        self.config = config
        splits_dir = yaml_config.timit_dataset_splits_dir
        partition = "TRAIN" if split == "train" else "TEST"
        data_folder = splits_dir + "/data/" + partition
        self.data: list[TimitA2PSeqSample] = []
        sample_folders = []
        self.g2p = G2p()
        for folder in os.listdir(data_folder):
            complete_path = data_folder + "/" + folder
            for sample_folder in os.listdir(complete_path):
                complete_sample_path = complete_path + "/" + sample_folder
                sample_folders.append(complete_sample_path)

        for folder in sample_folders:
            for sample in self._extractSampleDataFromFolder(folder):
                self.data.append(sample)

    def __getitem__(self, index) -> TimitA2PSeqSample:
        return self.data[index]

    def get_collate_fn(self):
        def _collate(samples: list[TimitA2PSeqSample]):
            max_audio_len = max([audio.size(0) for _, _, audio, _ in samples])

            padded_audio = [
                pad(
                    audio,
                    (0, max_audio_len - audio.size(0)),
                    mode="constant",
                    value=0,
                )
                for _, _, audio, _ in samples
            ]

            # ids already +1 for blank via get_phoneme_seq
            target_tensors = [
                torch.tensor(phoneme_ids) for phoneme_ids, _, _, _ in samples
            ]

            target_lens = [target_tensor.size(0) for target_tensor in target_tensors]
            max_target_len = max(target_lens)
            padded_targets = [
                pad(
                    target_tensor,
                    (0, max_target_len - target_tensor.size(0)),
                    mode="constant",
                    value=-1,
                )
                for target_tensor in target_tensors
            ]

            batch = TimitA2PSeqSampleBatch(
                input=torch.stack(padded_audio), target=torch.stack(padded_targets)
            )
            batch.transcripts = [transcript for _, transcript, _, _ in samples]
            batch.input_lens = torch.tensor(
                [audio.size(0) for _, _, audio, _ in samples]
            )
            batch.target_lens = torch.tensor(target_lens)
            batch.phonemes = [phonemes for _, _, _, phonemes in samples]
            return batch

        return _collate

    def __len__(self):
        return len(self.data)

    def _extractSampleDataFromFolder(self, folder: str) -> list[TimitA2PSeqSample]:
        sampleNames = [
            fileName.split(".")[0]
            for fileName in os.listdir(folder)
            if fileName.split(".")[-1] == "TXT"
        ]
        samples: list[TimitA2PSeqSample] = []
        for sampleName in sampleNames:
            transcriptFile = folder + "/" + sampleName + ".TXT"
            audioFile = folder + "/" + sampleName + ".WAV"

            transcript = self._readTranscript(transcriptFile)
            audio = self._readAudio(audioFile)
            phonemes = get_phoneme_seq(self.g2p, transcript, zero_is_blank=True)

            sample = TimitA2PSeqSample(
                phonemes.phoneme_ids,
                transcript,
                torch.tensor(audio, dtype=torch.float32),
                " ".join(phonemes.phonemes),
            )
            samples.append(sample)

        return samples

    def _readAudio(self, filePath: str) -> np.ndarray:
        # Frequency should be 16 kHz as used in the pretraining dataset of wav2vec
        # V. Panayotov, G. Chen, D. Povey, and S. Khudanpur. Librispeech: an asr corpus based on public
        # domain audio books. In Proc. of ICASSP, pages 5206–5210. IEEE, 2015.
        wav = soundfile.read(filePath)
        return np.array(wav[0])

    def _readTranscript(self, filePath: str) -> str:
        with open(filePath, "r") as f:
            transcript = " ".join(f.read().split(" ")[2:])

        transcript = transcript.upper()
        if self.config.remove_punctuation:
            chars_to_ignore_regex = r'[\,\?\.\!\-\;\:"]'
            transcript = re.sub(chars_to_ignore_regex, "", transcript)
        return transcript
