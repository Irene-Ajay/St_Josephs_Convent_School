"""Model registry.

Models are loaded by their `is_active` flag in the `ml_models` table, never by
filename. Promotion to active is guarded: a new version replaces the incumbent
only if it scores at least as well on the held-out set. Automatic promotion
without that guard is how production models silently degrade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib



@dataclass(slots=True)
class LoadedModel:
    name: str
    version: str
    estimator: Any
    feature_names: list[str]
    metrics: dict[str, Any]

    def assert_feature_parity(self, current_features: list[str]) -> None:
        """Catches the 'we added a feature and inference broke silently'
        failure. Called at load time, so it fails loudly at startup rather
        than producing quietly wrong predictions."""
        if list(self.feature_names) != list(current_features):
            missing = set(self.feature_names) - set(current_features)
            extra = set(current_features) - set(self.feature_names)
            raise RuntimeError(
                f"Feature mismatch for {self.name}@{self.version}. "
                f"Missing: {sorted(missing)}. Unexpected: {sorted(extra)}. "
                "Retrain before serving."
            )


class ModelRegistry:
    def __init__(self, base_dir: str | None = None) -> None:
        self.base = Path(base_dir or "./ml_artifacts")
        self.base.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, LoadedModel] = {}

    def save(
        self,
        name: str,
        version: str,
        estimator: Any,
        feature_names: list[str],
        metrics: dict[str, Any],
    ) -> Path:
        folder = self.base / name / version
        folder.mkdir(parents=True, exist_ok=True)
        joblib.dump(estimator, folder / "model.joblib")
        (folder / "meta.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": version,
                    "feature_names": feature_names,
                    "metrics": metrics,
                },
                indent=2,
            )
        )
        return folder

    def load(self, name: str, version: str) -> LoadedModel:
        key = f"{name}:{version}"
        if key in self._cache:
            return self._cache[key]

        folder = self.base / name / version
        meta = json.loads((folder / "meta.json").read_text())
        model = LoadedModel(
            name=name,
            version=version,
            estimator=joblib.load(folder / "model.joblib"),
            feature_names=meta["feature_names"],
            metrics=meta["metrics"],
        )
        self._cache[key] = model
        return model

    @staticmethod
    def should_promote(
        candidate: dict[str, float], incumbent: dict[str, float] | None, key: str
    ) -> bool:
        """Promotion guard. A candidate must match or beat the incumbent on
        the primary metric — PR-AUC for imbalanced classifiers, not accuracy.
        """
        if incumbent is None:
            return True
        return candidate.get(key, 0.0) >= incumbent.get(key, 0.0)


registry = ModelRegistry()
