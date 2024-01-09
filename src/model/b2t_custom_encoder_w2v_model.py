from src.model.b2tmodel import B2TModel, ModelOutput
from transformers import Wav2Vec2ForCTC, Wav2Vec2ForPreTraining
from transformers.modeling_outputs import CausalLMOutput
from src.args.wav2vec_args import (
    B2TWav2VecCustomEncoderArgsModel,
)
import torch
from typing import Optional, cast
from src.args.yaml_config import YamlConfigModel
from transformers import PreTrainedTokenizer
from transformers.models.wav2vec2.modeling_wav2vec2 import (
    Wav2Vec2ForPreTrainingOutput,
    Wav2Vec2FeatureEncoder,
)
from torch import nn
from transformers.activations import ACT2FN

IN_CHANNELS = 2
NUM_FEATURES = 128


class ConvLayer(nn.Module):
    def __init__(self, config: B2TWav2VecCustomEncoderArgsModel, layer_id=0):
        super().__init__()
        self.in_conv_dim = (
            config.conv_dim[layer_id - 1] if layer_id > 0 else IN_CHANNELS
        )
        self.out_conv_dim = config.conv_dim[layer_id]

        self.conv = nn.Sequential(
            nn.Conv2d(
                self.in_conv_dim,
                self.out_conv_dim,
                kernel_size=(config.conv_kernel[layer_id], NUM_FEATURES),
                stride=config.conv_stride[layer_id],
                bias=config.conv_bias,
            )
        )

    def forward(self, hidden_states):
        hidden_states = self.conv(hidden_states)

        return hidden_states.squeeze(-1)


class Wav2Vec2GroupNormConvLayer(nn.Module):
    def __init__(self, config: B2TWav2VecCustomEncoderArgsModel, layer_id=0):
        super().__init__()
        self.conv = ConvLayer(config, layer_id)
        self.activation = ACT2FN[config.feat_extract_activation]

        self.layer_norm = nn.GroupNorm(
            num_groups=self.conv.out_conv_dim,
            num_channels=self.conv.out_conv_dim,
            affine=True,
        )

    def forward(self, hidden_states):
        hidden_states = self.conv(hidden_states)
        hidden_states = self.layer_norm(hidden_states)
        hidden_states = self.activation(hidden_states)
        return hidden_states


class Wav2Vec2LayerNormConvLayer(nn.Module):
    def __init__(self, config: B2TWav2VecCustomEncoderArgsModel, layer_id=0):
        super().__init__()
        self.conv = ConvLayer(config, layer_id)
        self.layer_norm = nn.LayerNorm(self.conv.out_conv_dim, elementwise_affine=True)
        self.activation = ACT2FN[config.feat_extract_activation]

    def forward(self, hidden_states):
        hidden_states = self.conv(hidden_states)

        hidden_states = hidden_states.transpose(-2, -1)
        hidden_states = self.layer_norm(hidden_states)
        hidden_states = hidden_states.transpose(-2, -1)

        hidden_states = self.activation(hidden_states)
        return hidden_states


class Wav2Vec2NoLayerNormConvLayer(nn.Module):
    def __init__(self, config: B2TWav2VecCustomEncoderArgsModel, layer_id=0):
        super().__init__()
        self.conv = ConvLayer(config, layer_id)
        self.activation = ACT2FN[config.feat_extract_activation]

    def forward(self, hidden_states):
        hidden_states = self.conv(hidden_states)
        hidden_states = self.activation(hidden_states)
        return hidden_states


class FeatureEncoder(Wav2Vec2FeatureEncoder):
    """Construct the features from raw audio waveform"""

    def __init__(self, config: B2TWav2VecCustomEncoderArgsModel):
        super().__init__(config)

        if config.feat_extract_norm == "group":
            conv_layers = [Wav2Vec2GroupNormConvLayer(config, layer_id=0)] + [
                Wav2Vec2NoLayerNormConvLayer(config, layer_id=i + 1)
                for i in range(config.num_feat_extract_layers - 1)
            ]
        elif config.feat_extract_norm == "layer":
            conv_layers = [
                Wav2Vec2LayerNormConvLayer(config, layer_id=i)
                for i in range(config.num_feat_extract_layers)
            ]
        else:
            raise ValueError(
                f"`config.feat_extract_norm` is {config.feat_extract_norm}, but has to be one of ['group', 'layer']"
            )
        self.conv_layers = torch.nn.ModuleList(conv_layers)
        self.gradient_checkpointing = False
        self._requires_grad = True

    def forward(self, x: torch.Tensor):
        return super().forward(x)


class _CustomEncodeBaseW2VModel(B2TModel):
    def __init__(
        self,
        config: B2TWav2VecCustomEncoderArgsModel,
        yaml_config: YamlConfigModel,
        tokenizer: PreTrainedTokenizer,
    ):
        super().__init__()
        self.config = config
        assert (
            self.config.preprocessing == "seperate_zscoring_2channels"
        ), "Preprocessing must be seperate_zscoring_2channels for CustomFeatureEncoder model"
        self.tokenizer = tokenizer

    def _prepare_input(self, x: torch.Tensor, targets: Optional[torch.Tensor] = None):
        assert (
            len(x.size()) == 3 or len(x.size()) == 4
        ), f"x must be 3D shape: (channels=2, timestamps, brain_data=128) or 4D shape: (batch_size, channels=2, timestamps, brain_data=128) but has shape {x.size()}"

        is_batched = len(x.size()) == 4
        batched_input = x if is_batched else x.unsqueeze(0)
        # replace padding token with -100 for it to be ignored in ctc loss
        if targets is not None:
            targets = torch.where(
                targets == self.tokenizer.pad_token_id, torch.tensor(-100), targets
            )

        return batched_input, targets


class B2TCustomEncoderW2VPretrainingModel(_CustomEncodeBaseW2VModel):
    """Wav2Vec2 model with our own feature encoder, not requiring the data to be converted to audio shape"""

    def __init__(
        self,
        config: B2TWav2VecCustomEncoderArgsModel,
        yaml_config: YamlConfigModel,
        tokenizer: PreTrainedTokenizer,
    ):
        super().__init__(config, yaml_config, tokenizer)

        self.wav2vec2 = cast(
            Wav2Vec2ForPreTraining,
            Wav2Vec2ForPreTraining.from_pretrained(
                config.wav2vec_checkpoint,
                cache_dir=yaml_config.cache_dir,
                pad_token_id=tokenizer.pad_token_id,
            ),
        )
        self.wav2vec2.wav2vec2.feature_extractor = FeatureEncoder(config)

    def forward(
        self, x: torch.Tensor, targets: Optional[torch.Tensor] = None
    ) -> ModelOutput:
        batched_input, targets = self._prepare_input(x, targets)

        wav2vec2_out = cast(
            Wav2Vec2ForPreTrainingOutput,
            self.wav2vec2.forward(batched_input, return_dict=True),
        )
        metrics = (
            {"contrastive_loss": wav2vec2_out.loss.item()}
            if wav2vec2_out.loss is not None
            else {}
        )
        return ModelOutput(
            logits=torch.tensor([]), loss=wav2vec2_out.loss, metrics=metrics
        )


class B2TCustomEncoderW2VFineTuningModel(_CustomEncodeBaseW2VModel):
    """Wav2Vec2 model with our own feature encoder, not requiring the data to be converted to audio shape"""

    def __init__(
        self,
        config: B2TWav2VecCustomEncoderArgsModel,
        yaml_config: YamlConfigModel,
        tokenizer: PreTrainedTokenizer,
    ):
        super().__init__(config, yaml_config, tokenizer)
        self.wav2vec2 = cast(
            Wav2Vec2ForCTC,
            Wav2Vec2ForCTC.from_pretrained(
                config.wav2vec_checkpoint,
                cache_dir=yaml_config.cache_dir,
                ctc_loss_reduction=config.ctc_loss_reduction,
                pad_token_id=tokenizer.pad_token_id,
            ),
        )
        self.wav2vec2.wav2vec2.feature_extractor = FeatureEncoder(config)

    def forward(
        self, x: torch.Tensor, targets: Optional[torch.Tensor] = None
    ) -> ModelOutput:
        batched_input, targets = self._prepare_input(x, targets)

        wav2vec2_out = cast(
            CausalLMOutput,
            self.wav2vec2.forward(batched_input, return_dict=True),
        )
        metrics = (
            {"ctc_loss": wav2vec2_out.loss.item()}
            if wav2vec2_out.loss is not None
            else {}
        )
        return ModelOutput(
            logits=wav2vec2_out.logits, loss=wav2vec2_out.loss, metrics=metrics
        )
