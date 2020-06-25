from __future__ import annotations

import logging
import typing as T
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from pytorch_lightning.callbacks.early_stopping import EarlyStopping
from pytorch_lightning.core.lightning import LightningModule
from pytorch_lightning.loggers.base import LightningLoggerBase
from pytorch_lightning.metrics.functional import accuracy
from pytorch_lightning.trainer import seed_everything
from pytorch_lightning.trainer import Trainer
from sklearn.metrics import confusion_matrix
from torch import Tensor
from torch.utils.data import DataLoader
from torch.utils.data import Dataset
from tqdm import tqdm  # type: ignore

from Gat import data
from Gat import utils
from Gat.config import base as config
from Gat.loggers.wandb_logger import WandbLogger
from Gat.neural import models

# from pytorch_lightning.loggers import TensorBoardLogger


logger = logging.getLogger("__main__")

seed_everything(0)


class OneBatch(T.NamedTuple):
    word_ids: torch.Tensor
    batched_adj: torch.Tensor
    edge_types: torch.Tensor
    target: torch.Tensor


class LitGatForSequenceClassification(LightningModule):
    def __init__(
        self, all_config: config.EverythingConfig,
    ):
        super().__init__()
        self._all_config = all_config

        self.save_hyperparameters(self._all_config.as_flat_dict())

    def setup(self, stage: str) -> None:
        self._setup_data()
        self._setup_model()

    def _setup_data(self) -> None:
        preprop_config = self._all_config.preprop

        datasets, txt_srcs, word_vocab = data.load_splits(
            unk_thres=preprop_config.unk_thres,
            sent2graph_name=preprop_config.sent2graph_name,
            dataset_dir=Path(preprop_config.dataset_dir),
            lstxt_col=["sentence"],
            splits=["train", "val"],
        )

        for key, dataset in datasets.items():
            dataset = data.ConnectToClsDataset(dataset)
            if self._all_config.preprop.undirected:
                dataset = data.UndirectedDataset(dataset)
            datasets[key] = dataset

        self._datasets = datasets
        self._txt_srcs = txt_srcs
        self._word_vocab: data.BasicVocab = word_vocab

        # Set dataset dependent configuration
        self._all_config.model.dataset_dep = config.GATForSequenceClassificationDatasetDepConfig(
            num_classes=len(self._datasets["train"].vocab.labels.all_lbls),
            num_edge_types=len(self._datasets["train"].id2edge_type),
        )

    def _setup_model(self) -> None:
        model_config = self._all_config.model

        if model_config.node_embedding_type == "pooled_bert":
            sub_word_vocab: T.Optional[data.BertVocab] = data.BertVocab()
        else:
            sub_word_vocab = None

        self._gat_model = models.GATForSequenceClassification(
            model_config, word_vocab=self._word_vocab, sub_word_vocab=sub_word_vocab,
        )
        self._crs_entrpy = nn.CrossEntropyLoss()
        self._trainer_config = self._all_config.trainer

    def _collate_fn(self, lsgraph_example: T.List[utils.GraphExample]) -> OneBatch:
        """Turn `GraphExample` into a series of `torch.Tensor`s  """
        lslsgraph: T.List[T.List[utils.Graph]]
        lslbl_id: T.List[int]
        lslsgraph, lslbl_id = map(list, zip(*lsgraph_example))  # type: ignore

        # Since we're doing single sentence classification, we don't need additional
        # nesting
        lsgraph = [lsgraph[0] for lsgraph in lslsgraph]

        lslsedge: T.List[T.List[T.Tuple[int, int]]]
        lslsedge_type: T.List[T.List[int]]
        lslsimp_node: T.List[T.List[int]]
        lsnodeid2wordid: T.List[T.List[int]]

        lslsedge, lslsedge_type, lslsimp_node, lsnodeid2wordid = map(  # type: ignore
            list, zip(*lsgraph)
        )
        word_ids: torch.Tensor = self._word_vocab.prepare_for_embedder(
            lsnodeid2wordid, self._gat_model.word_embedder
        )
        word_ids.requires_grad_(False)
        # (B, L)

        B, L = word_ids.size()
        # Build the adjacnecy matrices
        batched_adj = torch.zeros([B, L, L], dtype=torch.bool)
        batched_adj.requires_grad_(False)

        # Build the edge types
        edge_types: torch.Tensor = torch.zeros(
            [B, L, L], dtype=torch.long,
        )
        edge_types.requires_grad_(False)
        edge_types.detach_()
        for batch_num, (lsedge, lsedge_type) in enumerate(zip(lslsedge, lslsedge_type)):
            indexing_arrs: T.Tuple[T.List[int], T.List[int]] = tuple(zip(*lsedge))  # type: ignore
            batched_adj[batch_num][indexing_arrs[0], indexing_arrs[1]] = 1
            edge_types[batch_num][indexing_arrs[0], indexing_arrs[1]] = torch.tensor(
                lsedge_type, dtype=torch.long
            )

        target = torch.tensor(lslbl_id, dtype=torch.long)
        # (B,)

        return OneBatch(
            word_ids=word_ids,
            batched_adj=batched_adj,
            edge_types=edge_types,
            target=target,
        )

    def train_dataloader(self) -> DataLoader[OneBatch]:
        res = DataLoader(
            dataset=self._datasets["train"],
            collate_fn=self._collate_fn,
            batch_size=self._trainer_config.train_batch_size,
            num_workers=8,
        )

        return res

    def val_dataloader(self) -> T.List[DataLoader[OneBatch]]:
        val_dataloader = DataLoader(
            self._datasets["val"],
            collate_fn=self._collate_fn,
            batch_size=self._trainer_config.eval_batch_size,
            num_workers=8,
        )

        cut_train_dataset = data.CutDataset(
            self._datasets["train"], total_len=len(self._datasets["val"])
        )
        cut_train_dataloader = DataLoader(
            cut_train_dataset,
            collate_fn=self._collate_fn,
            batch_size=self._trainer_config.eval_batch_size,
            num_workers=8,
        )

        self._val_dataset_names = ["val", "cut_train"]

        return [val_dataloader, cut_train_dataloader]

    def configure_optimizers(self) -> optim.optimizer.Optimizer:
        params = list(self.parameters())
        print(f"passing params of length: {len(params)}")
        return optim.Adam(params, lr=self._trainer_config.lr)

    def forward(
        self,
        word_ids: torch.Tensor,
        batched_adj: torch.Tensor,
        edge_types: torch.Tensor,
    ) -> torch.Tensor:
        logits = self._gat_model(word_ids, batched_adj, edge_types)
        return logits

    def __call__(
        self,
        word_ids: torch.Tensor,
        batched_adj: torch.Tensor,
        edge_types: torch.Tensor,
    ) -> torch.Tensor:
        return super().__call__(word_ids, batched_adj, edge_types)  # type: ignore

    def training_step(  # type: ignore
        self, batch: OneBatch, batch_idx: int
    ) -> T.Dict[str, T.Union[Tensor, T.Dict[str, Tensor]]]:
        logits = self(batch.word_ids, batch.batched_adj, batch.edge_types)
        loss = self._crs_entrpy(logits, batch.target)

        return {
            "loss": loss,
        }

    def validation_step(  # type: ignore
        self, batch: OneBatch, batch_idx: int, dataloader_idx: int = 0
    ) -> T.Dict[str, Tensor]:
        logits = self(batch.word_ids, batch.batched_adj, batch.edge_types)
        return {"logits": logits.detach(), "target": batch.target}

    def on_train_start(self) -> None:
        return
        one_example: OneBatch = next(iter(self.train_dataloader()))
        # NOTE: The tb logger must be the first
        self.logger[0].experiment.add_graph(
            self._gat_model,
            (one_example.word_ids, one_example.batched_adj, one_example.edge_types,),
        )

    def validation_epoch_end(
        self,
        outputs: T.Union[
            T.List[T.Dict[str, Tensor]], T.List[T.List[T.Dict[str, Tensor]]]
        ],
    ) -> T.Dict[str, T.Dict[str, Tensor]]:
        res: T.Dict[str, Tensor] = {}

        lslsoutput: T.List[T.List[T.Dict[str, Tensor]]]
        if isinstance(outputs[0], dict):
            lslsoutput = [outputs]  # type: ignore
        else:
            lslsoutput = outputs  # type: ignore
        for i, lsoutput in enumerate(lslsoutput):
            val_dataset_name = self._val_dataset_names[i]
            all_logits = torch.cat([output["logits"] for output in lsoutput])
            # (B, C)
            all_target = torch.cat([output["target"] for output in lsoutput])
            # (B,)

            all_preds = all_logits.argmax(dim=1)
            # (B,)
            acc = accuracy(all_preds, all_target)
            res.update({f"{val_dataset_name}_acc": acc})

        return {"progress_bar": res, "log": res}

    """
    def on_train_end(self) -> None:
        return
        self.analyze_predict(
            logits=val_logits,
            true_=val_true,
            ds=val_dataset,
            txt_src=self._txt_srcs[self._val_name],
        )

    def analyze_predict(
        self,
        logits: np.ndarray,
        true_: np.ndarray,
        txt_src: data.TextSource,
        ds: data.SentenceGraphDataset,
    ) -> None:
        preds: np.ndarray = logits.argmax(axis=1)
        matches: np.ndarray = np.equal(preds, true_)
        table_rows: T.List[T.Tuple[utils.Cell, ...]] = [
            (
                utils.TextCell(txt_src[i].lssent[0]),
                utils.SvgCell(ds.sentgraph_to_svg(ds[i].lssentgraph[0])),
                utils.NumCell(preds[i]),
                utils.NumCell(ds[i].lbl_id),
            )
            for i in range(preds.shape[0])
        ]
        row_colors = [None if i else "red" for i in matches]
        table_html = utils.html_table(
            rows=table_rows,
            headers=tuple(
                utils.TextCell(i)
                for i in ["Original", "Tokenized Parse", "Predicted", "Gold"]
            ),
            row_colors=row_colors,
        )

        cm = confusion_matrix(true_, preds, labels=range(len(self.vocab.id2lbl)))
        cm_plot = utils.plotly_cm(cm, labels=self.vocab.id2lbl)
        self.logger.log(
            {
                "val_preds": wandb.Html(table_html, inject=False),
                "confusion_matrix": cm_plot,
            }
        )
        """


def main() -> None:
    all_config = config.EverythingConfig(
        trainer=config.TrainerConfig(
            lr=2e-5, train_batch_size=128, eval_batch_size=128, epochs=40,
        ),
        preprop=config.PreprocessingConfig(
            undirected=True,
            # dataset_dir="actual_data/SST-2_tiny",
            dataset_dir="actual_data/SST-2_small",
            # dataset_dir="actual_data/SST-2",
            # dataset_dir="actual_data/glue_data/SST-2",
            # dataset_dir="actual_data/paraphrase/paws_small",
            sent2graph_name="srl",
        ),
        model=config.GATForSequenceClassificationConfig(
            embedding_dim=768,
            gat_layered=config.GATLayeredConfig(
                num_heads=12, intermediate_dim=768, feat_dropout_p=0.3, num_layers=4,
            ),
            node_embedding_type="pooled_bert",
            use_edge_features=True,
            dataset_dep=None,
        ),
    )

    early_stop_callback: T.Optional[EarlyStopping] = None
    if all_config.trainer.early_stop_patience > 0:
        early_stop_callback = EarlyStopping(
            monitor="val_acc",
            min_delta=0.00,
            patience=all_config.trainer.early_stop_patience,
            verbose=False,
            mode="max",
        )

    model = LitGatForSequenceClassification(all_config)

    loggers: T.List[LightningLoggerBase] = []
    wandb_logger = WandbLogger(project="gat", sync_tensorboard=True)
    # tb_logger = TensorBoardLogger(save_dir=wandb_logger.experiment.dir)
    # TB logger must be first
    # loggers.append(tb_logger)
    loggers.append(wandb_logger)
    trainer = Trainer(
        logger=loggers,
        max_epochs=all_config.trainer.epochs,
        gpus=1,
        early_stop_callback=early_stop_callback,
    )

    trainer.fit(model)


if __name__ == "__main__":
    logging.basicConfig()
    logger.setLevel(logging.INFO)
    main()
