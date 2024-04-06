from torch.optim.optimizer import Optimizer
from src.datasets.batch_types import SampleBatch
from src.model.b2tmodel import ModelOutput
from src.args.base_args import B2TArgsModel
from src.datasets.brain2text import Brain2TextDataset
from src.experiments.experiment import Experiment
from src.args.yaml_config import YamlConfigModel
from typing import Any, Literal, cast
from transformers import AutoTokenizer
from transformers import PreTrainedTokenizer
from torch.utils.data import DataLoader
from src.train.evaluator import DefaultEvaluator
from src.train.history import DecodedPredictionBatch
from src.util.batch_sampler import Brain2TextBatchSampler


class B2TExperiment(Experiment):
    def __init__(self, config: dict, yamlConfig: YamlConfigModel):
        self.config = self.get_args_model()(**config)
        self.tokenizer = cast(PreTrainedTokenizer, self._create_tokenizer())
        super().__init__(config, yamlConfig)

    def get_name(self) -> str:
        raise NotImplementedError()

    @staticmethod
    def get_args_model():
        return B2TArgsModel

    def _create_tokenizer(self):
        if self.config.tokenizer == "wav2vec_pretrained":
            assert (
                not self.config.tokenizer_checkpoint is None
            ), "Tokenizer checkpoint (--tokenizer_checkpoint) must be set when using --tokenizer=wav2vec_pretrained"

            return AutoTokenizer.from_pretrained(
                self.config.tokenizer_checkpoint,
                cache_dir=self.yaml_config.cache_dir,
            )
        raise Exception(f"Tokenizer {self.config.tokenizer} not supported yet")

    def _create_model(self):
        raise NotImplementedError()

    def decode_predictions(
        self, predictions: ModelOutput, sample: SampleBatch
    ) -> DecodedPredictionBatch:
        predicted_ids = predictions.logits.argmax(dim=-1).cpu().numpy()
        predicted_strings = self.tokenizer.batch_decode(
            predicted_ids, group_tokens=True
        )
        label_strings = (
            self.tokenizer.batch_decode(sample.target.cpu().numpy(), group_tokens=False)
            if sample.target is not None
            else None
        )
        return DecodedPredictionBatch(predicted_strings, label_strings)

    def create_optimizer(self) -> Optimizer:
        def get_trainable_params():
            return self.model.parameters()

        optim: Any = self._get_optimizer_cls()
        return optim(get_trainable_params(), lr=self.config.learning_rate)

    def _create_dataset(self, split: Literal["train", "val", "test"] = "train"):
        return Brain2TextDataset(
            config=self.config,
            yaml_config=self.yaml_config,
            split=split,
            tokenizer=self.tokenizer,
        )

    def _create_dataloader(self, split: Literal["train", "val", "test"]) -> DataLoader:
        ds = self._create_dataset(split)

        batch_sampler = Brain2TextBatchSampler(ds, self.base_config.batch_size)

        return DataLoader(
            self._create_dataset(split),
            batch_sampler=batch_sampler,
            collate_fn=ds.get_collate_fn(self.tokenizer),
        )

    def get_vocab(self) -> list[str]:
        return self.tokenizer.convert_ids_to_tokens(
            list(range(self.tokenizer.vocab_size))
        )

    def create_evaluator(self, mode: Literal["train", "val", "test"]):
        return DefaultEvaluator(self.tokenizer, mode)
