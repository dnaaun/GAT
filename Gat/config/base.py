from __future__ import annotations

import inspect
import typing as T

import typing_extensions as TT


_ConfigType = T.TypeVar("_ConfigType", bound="Config")


class Config:
    def __init__(self) -> None:
        self._did__init__ = True
        self._validate()

    def __setattr__(
        self, n: str, v: T.Optional[T.Union["Config", int, float, str]]
    ) -> None:
        # Some introspection to get arguments from __init__
        init_signature = inspect.signature(self.__class__.__init__)
        init_param_names = init_signature.parameters.keys()

        if n not in init_param_names and n != "_did__init__":
            raise Exception(
                f"{n} is not a valid confiugration for {self.__class__.__name__}"
            )

        super().__setattr__(n, v)

        # Don't _validate during __init__ since some things are not yet set yet
        if hasattr(self, "_did__init__"):
            self._validate()

    def __repr__(self) -> str:
        return repr(f"{self.__class__}.from_dict({self.as_dict()})")

    @classmethod
    def from_dict(cls: T.Type[_ConfigType], d: T.Dict[str, T.Any]) -> _ConfigType:
        raise NotImplementedError()

    def as_dict(self) -> T.Dict[str, T.Any]:
        """Turn this config into a dictionary, recursively."""
        d: T.Dict[str, T.Any] = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Config):
                d[k] = v.as_dict()
            else:
                d[k] = v
        return d

    def as_flat_dict(self, sep: str = ".") -> T.Dict[str, T.Any]:
        """Turn this config into a dictionary.

        If further Config instances found as values in this config, deal as follows: 

        Args:
            sep: The seprarator to use. Checkout the example below.

        >>> big = BigConfig(
                model=ModelConfig(embedding_dim=300),
                trainer=TrainerConfig(epochs=4)
                use_gpu=True,
            )
        >>> big.as_flat_dict()
        {
                "model.embedding_dim": 300,
                "trainer.epochs": 4,
                "use_gpu": True,
        }
        """
        result: T.Dict[str, T.Any] = {}

        for key, value in self.__dict__.items():
            if isinstance(value, Config):
                for child_key, value in value.as_flat_dict().items():
                    final_key = key + sep + child_key
                    result[final_key] = value
            else:
                result[key] = value

        return result

    def _validate(self) -> None:
        """Raise an exception if the config is invalid."""
        pass


class TrainerConfig(Config):
    def __init__(
        self,
        lr: float,
        epochs: int,
        train_batch_size: int,
        eval_batch_size: int,
        use_cuda: bool = True,
        early_stop_patience: int = 3,
        do_eval_every_epoch: bool = True,
        do_eval_on_truncated_train_set: bool = True,
    ):
        """Look as superclass doc."""
        self.lr = lr
        self.use_cuda = use_cuda
        self.epochs = epochs
        self.do_eval_every_epoch = do_eval_every_epoch
        self.eval_batch_size = eval_batch_size
        self.train_batch_size = train_batch_size
        self.early_stop_patience = early_stop_patience
        self.do_eval_on_truncated_train_set = do_eval_on_truncated_train_set
        super().__init__()


class GATLayeredConfig(Config):
    def __init__(
        self,
        num_heads: int,
        intermediate_dim: int,
        num_layers: int,
        edge_dropout_p: float = 0.0,
        feat_dropout_p: float = 0.3,
        rezero_or_residual: TT.Literal["rezero", "residual"] = "rezero",
    ):
        """Look at superclass doc."""

        self.intermediate_dim = intermediate_dim
        self.num_layers = num_layers
        self.num_heads = num_heads
        self.edge_dropout_p = edge_dropout_p
        self.feat_dropout_p = feat_dropout_p
        self.rezero_or_residual = rezero_or_residual
        super().__init__()


class GATForSequenceClassificationDatasetDepConfig(Config):
    def __init__(
        self, num_classes: int, num_edge_types: int,
    ):
        self.num_classes = num_classes
        self.num_edge_types = num_edge_types
        super().__init__()


class GATForSequenceClassificationConfig(Config):
    def __init__(
        self,
        gat_layered: GATLayeredConfig,
        embedding_dim: int,
        node_embedding_type: T.Literal["pooled_bert", "basic", "bpe"],
        use_pretrained_embs: bool,
        use_edge_features: bool,
        dataset_dep: T.Optional[GATForSequenceClassificationDatasetDepConfig],
        bpe_vocab_size: T.Optional[T.Literal[25000]] = None,
    ):
        self.embedding_dim = embedding_dim
        self.gat_layered = gat_layered
        self.node_embedding_type = node_embedding_type
        self.use_pretrained_embs = use_pretrained_embs
        self.use_edge_features = use_edge_features
        self.dataset_dep = dataset_dep
        self.bpe_vocab_size = bpe_vocab_size
        super().__init__()

    def _validate(self) -> None:
        if self.node_embedding_type == "pooled_bert":
            assert self.use_pretrained_embs, "pooled bert means using pretrained"

        if self.node_embedding_type == "bpe":
            assert self.bpe_vocab_size is not None
        else:
            assert self.bpe_vocab_size is None


class PreprocessingConfig(Config):
    def __init__(
        self,
        undirected: bool,
        dataset_dir: str,
        sent2graph_name: TT.Literal["dep", "srl"],
        unk_thres: T.Optional[int] = 1,
    ) -> None:
        self.sent2graph_name = sent2graph_name
        self.dataset_dir = dataset_dir
        self.undirected = undirected
        self.unk_thres = unk_thres
        super().__init__()


class EverythingConfig(Config):
    def __init__(
        self,
        trainer: TrainerConfig,
        preprop: PreprocessingConfig,
        model: GATForSequenceClassificationConfig,
    ):
        self.trainer = trainer
        self.model = model
        self.preprop = preprop
        super().__init__()

    def _validate(self) -> None:
        if self.model.node_embedding_type in ["pooled_bert", "bpe"]:
            assert (
                self.preprop.unk_thres is None
            ), "why have UNK tokens if we're doing subword tokenization?"
