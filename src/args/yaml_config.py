from typing import Optional
import yaml
import os
from pydantic import BaseModel, Field

default_value = "<your value here>"


class YamlConfigModel(BaseModel):
    cache_dir: str = Field(
        description="Directory to store larger temporary files like model checkpoints in"
    )
    fig_dir: str = Field(description="Directory to store figures in")
    n3gram_lm_model_path: str = Field(description="Path to the 3-gram language model")
    n5gram_lm_model_path: str = Field(description="Path to the 5-gram language model")
    dataset_splits_dir: str = Field(
        description="Directory containing the original train and test split folder"
    )
    wandb_api_key: str = Field(
        description="Your Weights and Biases API key. You can find it in your W&B account settings."
    )
    wandb_project_name: str = Field(
        default="brain2text", description="Your W&B project name."
    )
    wandb_entity: str = Field(
        default="machine-learning-hpi", description="Your W&B entity name."
    )
    timit_dataset_splits_dir: str = Field(
        description="Directory containing the original train and test split folder of TIMIT dataset"
    )
    elevenlabs_api_key: Optional[str] = Field(
        description="Your Elevenlabs API key. You can find it in your Elevenlabs account settings. Needed if you like to run latent_analysis.ipynb"
    )
    latent_analysis_working_dir: str = Field(
        default="/hpi/fs00/scratch/tobias.fiedler/brain2text/latent_analysis"
    )


class YamlConfig:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as f:
                print(
                    f"\nCreated a {self.config_path} file in project root. Please replace the autogenerated values in it."
                )
                for name, field in YamlConfigModel.__fields__.items():
                    f.write(
                        f"{name}: {field.default if field.default is not None else default_value}\n"
                    )
                exit(0)
        with open(self.config_path, "r") as f:
            file_content = yaml.safe_load(f)
            try:
                return YamlConfigModel(**file_content)
            except Exception as e:
                raise Exception(
                    f"Error validating fields in config file {self.config_path}: \n{e}"
                )
