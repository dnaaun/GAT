import logging
import random
from pathlib import Path
from pprint import pformat
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import TypeVar

import numpy as np
import sklearn.metrics as skmetrics
import torch
import torch.nn as nn
import torch.optim as optim
from torch import Tensor
from torch.utils.data import DataLoader
from torch.utils.data import Dataset
from tqdm import tqdm

import wandb  # type: ignore
from config import EverythingConfig
from config import GATForSeqClsfConfig
from config import TrainConfig
from data import load_splits
from data import SentenceGraphDataset
from data import SliceDataset
from data import VocabAndEmb
from models import GATForSeqClsf


logger = logging.getLogger("__main__")

random.seed(0)
np.random.seed(0)
torch.manual_seed(0)  # type: ignore

_T = TypeVar("_T")


def _prefix_keys(d: Dict[str, _T], prefix: str) -> Dict[str, _T]:
    return {f"{prefix}_{k}": v for k, v in d.items()}


class Trainer:
    def __init__(self, train_config: TrainConfig) -> None:
        self.config = train_config
        self._prepare_data()

    def _prepare_data(self) -> None:
        self._val_name = "dev"
        datasets, txt_srcs, vocab_and_emb = load_splits(
            Path(self.config.dataset_dir),
            lstxt_col=["sentence"],
            splits=["train", self._val_name],
        )

        self._datasets = datasets
        self._txt_srcs = txt_srcs
        self._vocab_and_emb = vocab_and_emb

    @property
    def train_dataset(self) -> Dataset:  # type: ignore
        return self._datasets["train"]

    @property
    def val_dataset(self) -> Dataset:  # type: ignore
        return self._datasets[self._val_name]

    @property
    def vocab_and_emb(self) -> VocabAndEmb:
        return self._vocab_and_emb

    def train(self, model: GATForSeqClsf,) -> None:
        # Model and optimizer
        if self.config.use_cuda:
            model.cuda()

        wandb.watch(model)

        optimizer = optim.Adam(model.parameters(), lr=self.config.lr)

        train_dataset, val_dataset = (
            self._datasets["train"],
            self._datasets[self._val_name],
        )
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.train_batch_size,
            collate_fn=SentenceGraphDataset.collate_fn,
        )

        examples_seen = 0
        batches_seen = 0

        train_dataset_slice = SliceDataset(train_dataset, n=len(val_dataset))
        val_metrics, _, _ = self.evaluate(model, val_dataset)
        val_metrics = _prefix_keys(val_metrics, "val")
        logger.info(f"Before training | val: {val_metrics}")
        running_loss = torch.tensor(
            0, dtype=torch.float, device=next(model.parameters()).device
        )
        for epoch in range(1, self.config.epochs + 1):
            pbar_desc = f"epoch: {epoch}"
            pbar = tqdm(train_loader, desc=pbar_desc)
            for X, y in pbar:
                prepared_X = model.prepare_batch(X)
                running_loss += train_one_step(model, optimizer, prepared_X, y)
                examples_seen += self.config.train_batch_size
                batches_seen += 1
                pbar.set_description(
                    f"{pbar_desc} | train loss running: {(running_loss / batches_seen).item()}"
                )

            if self.config.do_eval_every_epoch:
                val_metrics, val_logits, val_true = self.evaluate(model, val_dataset)
                train_metrics, _, _ = self.evaluate(model, train_dataset_slice)

                all_metrics = dict(
                    **_prefix_keys(val_metrics, "val"),
                    **_prefix_keys(train_metrics, "train"),
                )
                wandb.log(all_metrics, step=examples_seen)
                logger.info(pformat(all_metrics))

                self.analyze_predict(
                    logits=val_logits, true_=val_true,
                )

        if not self.config.do_eval_every_epoch:
            val_metrics, val_logits, val_true = self.evaluate(model, val_dataset)
            train_metrics, _, _ = self.evaluate(model, train_dataset_slice)

            all_metrics = dict(
                **_prefix_keys(val_metrics, "val"),
                **_prefix_keys(train_metrics, "train"),
            )

        # Computed in either the for loop or after the for loop
        wandb.log(all_metrics)
        logger.info(pformat(all_metrics))

        self.analyze_predict(
            logits=val_logits, true_=val_true,
        )

    def evaluate(
        self, model: GATForSeqClsf, dataset: Dataset  # type: ignore
    ) -> Tuple[Dict[str, float], np.ndarray, np.ndarray]:

        val_loader = DataLoader(
            dataset,
            batch_size=self.config.eval_batch_size,
            collate_fn=SentenceGraphDataset.collate_fn,
        )

        model.eval()
        with torch.no_grad():
            loss = torch.tensor(
                0, dtype=torch.float, device=next(model.parameters()).device
            )
            all_logits: Optional[np.ndarray] = None
            all_true: Optional[np.ndarray] = None
            for X, y in val_loader:
                prepared_X = model.prepare_batch(X)
                logits, one_step_loss = model(prepared_X=prepared_X, y=y)
                loss += one_step_loss

                if all_logits is None:
                    all_logits = logits.detach().cpu().numpy()
                    all_true = np.array(y)
                else:
                    all_logits = np.concatenate(
                        [all_logits, logits.detach().cpu().numpy()], axis=0
                    )
                    all_true = np.concatenate([all_true, np.array(y)], axis=0)

        all_preds = np.argmax(all_logits, axis=1)
        acc: float = skmetrics.accuracy_score(all_true, all_preds)
        loss /= len(val_loader)
        metrics = {
            "loss": float(loss.item()),
            "acc": acc,
        }

        assert all_logits is not None
        assert all_true is not None
        return (metrics, all_logits, all_true)

    def analyze_predict(self, logits: np.ndarray, true_: np.ndarray) -> None:
        return
        # matches: np.ndarray = logits == true_
        # correct_indices = matches.nonzero()
        # incorrect_indices = (~matches).nonzero()


def train_one_step(
    model: nn.Module, optimizer: optim.Optimizer, prepared_X: Any, y: Any  # type: ignore
) -> Tensor:
    model.train()  # Turn on the train mode
    optimizer.zero_grad()
    logits, loss = model(prepared_X=prepared_X, y=y)
    loss.backward()
    # Clipping here maybe?
    optimizer.step()
    return loss  # type: ignore


def main() -> None:
    trainer_config = TrainConfig(
        lr=1e-3,
        train_batch_size=128,
        eval_batch_size=128,
        epochs=20,
        dataset_dir="data/glue_data/SST-2",
    )

    trainer = Trainer(trainer_config)

    model_config = GATForSeqClsfConfig(
        vocab_size=trainer.vocab_and_emb.embs.size(0),
        cls_id=trainer.vocab_and_emb._cls_id,
        nhid=50,
        nheads=6,
        embedding_dim=300,
        feat_dropout_p=0.3,
        nclass=len(trainer.vocab_and_emb._id2lbl),
        nmid_layers=6,
        nedge_type=len(trainer.val_dataset.sent2graph.id2edge_type),  # type: ignore
    )

    all_config = EverythingConfig(trainer=trainer_config, model=model_config)
    logger.info("About to try: " + pformat(all_config))

    model = GATForSeqClsf(all_config.model, emb_init=trainer.vocab_and_emb.embs)
    wandb.init(project="gat", config=all_config.as_dict())

    trainer.train(model)


if __name__ == "__main__":
    logging.basicConfig()
    logger.setLevel(logging.INFO)
    main()
