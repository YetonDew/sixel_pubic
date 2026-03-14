import yaml
from pathlib import Path

class Config:
    def __init__(self):
        with open("config/settings.yaml", "r") as f:
            self.cfg = yaml.safe_load(f)

    def get(self, path: str):
        keys = path.split(".")
        value = self.cfg
        for k in keys:
            value = value[k]
        return value

CONFIG = Config()
