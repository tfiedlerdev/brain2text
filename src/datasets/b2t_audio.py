from typing import Any, Literal, Callable
from matplotlib import scale
from torch.utils.data import Dataset
import os
from scipy.io import loadmat
from pathlib import Path
import torch
import numpy as np
from src.args.b2t_audio_args import B2TAudioDatasetArgsModel
from src.args.yaml_config import YamlConfigModel
from src.args.base_args import B2TDatasetArgsModel
from src.datasets.preprocessing import (
    preprocess_competition_recommended,
    preprocess_seperate_zscoring,
)
from tqdm import tqdm
import torch.nn.functional as F
from math import ceil

PreprocessingFunctions: dict[
    str,
    Callable[[dict, list[np.ndarray[Any, np.dtype[np.int32]]]], tuple[list, list[str]]],
] = {
    "competition_recommended": preprocess_competition_recommended,
    "seperate_zscoring": preprocess_seperate_zscoring,
}


def rolling_mean_tensor(kernel_size, tensor):
    kernel = torch.ones(kernel_size) / kernel_size
    kernel = kernel.cuda().float()

    return torch.nn.functional.conv1d(
        tensor.float().view(1, 1, -1),
        kernel.view(1, 1, -1),
        padding=kernel_size // 2,
    ).view(-1)[1:]


def b2t_audio_transformation(
    spike_pows, spike_counts, smoothing_window, audio_smoothing_window
):
    spike_pows = rolling_mean_tensor(smoothing_window, spike_pows)
    spike_counts = rolling_mean_tensor(smoothing_window, spike_counts)

    min_spike_count = spike_counts.min()
    spike_counts = (
        spike_counts
        + torch.full(
            size=spike_counts.size(), fill_value=min_spike_count.abs().item()
        ).cuda()
    )
    spike_counts = spike_counts * 50
    frequencies = spike_counts.int()

    min_spike_power = spike_pows.min()
    amplitudes = (
        spike_pows
        + torch.full(
            size=spike_pows.size(), fill_value=min_spike_power.abs().item()
        ).cuda()
    )

    # Constructing synthetic signal
    sum_freqs = frequencies.sum()
    time_stamps = np.zeros(sum_freqs)
    signal = np.zeros(sum_freqs)
    frequencies = frequencies.cpu().numpy()
    pos = True
    orig_spacing = 20.0

    idx = 0
    for i in range(len(frequencies)):
        freq = frequencies[i]
        if freq != 0:
            time_stamp_offset = orig_spacing / freq
            for j in range(freq):
                time_stamps[idx] = orig_spacing * i + j * time_stamp_offset
                signal[idx] = 1 if pos else -1
                pos = not pos
                idx = idx + 1

    # Time stamp unit is in ms, we convert to s
    time_stamps = time_stamps / 1000

    end_time = time_stamps[-1]
    target_freq_s = 1.0 / 16000
    new_x = np.arange(0, end_time + target_freq_s, target_freq_s)
    new_y = np.interp(new_x, time_stamps, signal)
    # Interpolating amplitudes for smoother amplitude in synthetic signal
    amplitudes = amplitudes.unsqueeze(0).unsqueeze(0)
    amp_interp = F.interpolate(input=amplitudes, size=len(new_x), mode="linear")
    amp_interp = amp_interp.squeeze()

    res_signal = amp_interp * torch.from_numpy(new_y).cuda()

    res_signal = rolling_mean_tensor(audio_smoothing_window, res_signal)

    return res_signal


class B2TAudioDataset(Dataset):
    def __init__(
        self,
        config: B2TAudioDatasetArgsModel,
        yaml_config: YamlConfigModel,
        split: Literal["train", "val", "test"] = "train",
    ) -> None:
        super().__init__()
        self.config = config

        if split == "val":
            data_path = Path(yaml_config.dataset_splits_dir) / "test"
        elif split == "test" and config.competition_mode:
            data_path = Path(yaml_config.dataset_splits_dir) / "competitionHoldOut"
        else:
            data_path = Path(yaml_config.dataset_splits_dir) / "train"

        if not os.path.exists(data_path):
            raise Exception(f"{data_path} does not exist.")

        data_files = [
            loadmat(data_path / fileName) for fileName in os.listdir(data_path)
        ]

        print("Loaded raw data")

        self.transcriptions: list[str] = []
        brain_data_samples: list[torch.Tensor] = []
        preprocess = PreprocessingFunctions[config.preprocessing]

        print("Preprocessing brain data and sentence data")
        for data_file in tqdm(data_files):
            # block-wise feature normalization
            blockNums = np.squeeze(data_file["blockIdx"])
            blockList = np.unique(blockNums)

            if split == "test" and not config.competition_mode:
                blockList = [blockList[0]]
            if split == "train" and not config.competition_mode:
                blockList = blockList[1:]

            blocks = []
            for b in range(len(blockList)):
                sentIdx = np.argwhere(blockNums == blockList[b])
                sentIdx = sentIdx[:, 0].astype(np.int32)
                blocks.append(sentIdx)

            input_features, transcriptions = preprocess(data_file, blocks)

            for dataSample in input_features:
                brain_data_samples.append(torch.tensor(dataSample, dtype=torch.float32))
            for sentence in transcriptions:
                self.transcriptions.append(f"<s>{sentence.upper()}</s>")

        if self.config.limit_samples is not None:
            brain_data_samples = brain_data_samples[: config.limit_samples]
            self.transcriptions = self.transcriptions[: config.limit_samples]

        print("Converting to sound waves")
        self.soundwaves: list[torch.Tensor] = []
        for sample in tqdm(brain_data_samples):
            if self.config.mean_reduction:
                spike_powers = sample[:, :128].mean(-1).cuda()
                spike_counts = sample[:, 128:].mean(-1).cuda()
                y = b2t_audio_transformation(
                    spike_powers,
                    spike_counts,
                    self.config.smoothing_window,
                    self.config.audio_smoothing_window,
                )
            else:
                sound_arrays = []
                neuron_count = 128
                for i in range(neuron_count):
                    spike_powers = sample[:, i].cuda()
                    spike_counts = sample[:, 128 + i].cuda()
                    neuron_y = b2t_audio_transformation(
                        spike_powers,
                        spike_counts,
                        self.config.smoothing_window,
                        self.config.audio_smoothing_window,
                    )
                    sound_arrays.append(neuron_y)
                min_len = min([wave.size(0) for wave in sound_arrays])
                # Resampling sometimes results in different size arrays
                sound_arrays = [sound_array[:min_len] for sound_array in sound_arrays]
                y = torch.stack(sound_arrays, dim=-1)
            self.soundwaves.append(y.float().cpu())

        assert len(self.transcriptions) == len(
            self.soundwaves
        ), "Length of labels and data samples must be equal."

    def __len__(self):
        return (
            len(self.transcriptions)
            if self.config.limit_samples is None
            else self.config.limit_samples
        )

    def __getitem__(self, index) -> tuple[torch.Tensor, str]:
        return self.soundwaves[index], self.transcriptions[index]
