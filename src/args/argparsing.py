import argparse
from src.experiments.suc_approach.C__discriminator_experiment import (
    DiscriminatorExperiment,
)
from src.experiments.suc_approach.B__b2p_suc_experiment import B2PSUCExperiment
from src.experiments.suc_approach.A__timit_w2v_suc_ctc_experiment import (
    TimitW2VSUC_CTCExperiment,
)
from src.experiments.suc_approach.timit_w2v_suc_experiment import TimitW2VSUCExperiment
from src.experiments.b2p2t_mvtst_experiment import B2P2TMvtstExperiment
from src.experiments.b2p2t_gru_experiment import B2P2TGruExperiment
from src.experiments.b2p2t_mamba_experiment import B2P2TMambaExperiment
from src.experiments.mvts_transformer_experiment import MvtsTransformerExperiment
from src.experiments.b2t_mamba_experiment import B2tMambaExperiment
from src.experiments.b2t_gru_experiment import B2tGruExperiment
from src.experiments.b2t_direct_cnn_experiment import CNNExperiment
from src.experiments.audio_wav2vec_experiment import AudioWav2VecExperiment
from src.experiments.b2t_audio_wav2vec_experiment import B2TAudioWav2VecExperiment
from src.experiments.experiment import Experiment
from pydantic import BaseModel
from src.args.base_args import BaseExperimentArgsModel
from typing import Any, Literal, Type, cast
from src.args.yaml_config import YamlConfig
from src.experiments.onehotindex_fc_experiment import OneHotIndexExperiment
from src.experiments.suc_approach.D__b2t_gru_w2v_experiment import (
    B2TGruAndW2VExperiment,
)

experiments: dict[str, Type[Experiment]] = {
    "audio_wav2vec2": AudioWav2VecExperiment,
    "b2t_audio_wav2vec": B2TAudioWav2VecExperiment,
    "onehot_index": OneHotIndexExperiment,
    "b2t_cnn": CNNExperiment,
    "b2t_gru": B2tGruExperiment,
    "mvts_transformer": MvtsTransformerExperiment,
    "b2t_mamba": B2tMambaExperiment,
    "b2p2t_mamba": B2P2TMambaExperiment,
    "b2p2t_gru": B2P2TGruExperiment,
    "b2p2t_mvtst": B2P2TMvtstExperiment,
    "timit_w2v_suc_ctc": TimitW2VSUC_CTCExperiment,
    "timit_w2v_suc": TimitW2VSUCExperiment,
    "b2p_suc": B2PSUCExperiment,
    "discriminator": DiscriminatorExperiment,
    "b2p2t_gru+w2v": B2TGruAndW2VExperiment,
}


def str_to_bool(value):
    if value.lower() in ["true", "t"]:
        return True
    elif value.lower() in ["false", "f"]:
        return False
    elif value.lower() in ["none", "n"]:
        return None
    else:
        raise argparse.ArgumentTypeError("Invalid boolean value: {}".format(value))


def str_to_list(value):
    import json

    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise argparse.ArgumentTypeError("Invalid list value: {}".format(value))
    return parsed


def _parser_from_model(parser: argparse.ArgumentParser, model: Type[BaseModel]):
    "Add Pydantic model to an ArgumentParser"
    fields = model.__fields__

    for name, field in fields.items():

        def get_type_args():
            is_literal = getattr(field.annotation, "__origin__", None) is Literal
            is_bool = getattr(field.type_, "__name__", None) == "bool"
            is_list = getattr(field.outer_type_, "__name__", None) == "list"

            if is_literal:
                return {"type": str, "choices": cast(Any, field.annotation).__args__}
            if is_bool:
                return {"type": str_to_bool}
            if is_list:
                return {"type": str_to_list}
            return {"type": field.type_}

        parser.add_argument(
            f"--{name}",
            dest=name,
            default=field.default,
            help=field.field_info.description,
            **get_type_args(),
        )
    return parser


def _create_arg_parser():
    base_parser = argparse.ArgumentParser()
    base_parser = _parser_from_model(base_parser, BaseExperimentArgsModel)
    base_args, _ = base_parser.parse_known_args()

    experiment_model = experiments[base_args.experiment_type].get_args_model()
    parser = argparse.ArgumentParser(
        description="Machine Learning Experiment Configuration"
    )
    parser = _parser_from_model(parser, experiment_model)
    return parser


def get_experiment_from_args() -> Experiment:
    arg_parser = _create_arg_parser()
    args = arg_parser.parse_args()
    yaml_config = YamlConfig()

    experiment = experiments[args.experiment_type](vars(args), yaml_config.config)
    return experiment
