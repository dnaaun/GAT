"""Tests for base.py."""
import tempfile
from pathlib import Path

import pytest
import torch

from Gat import data
from Gat import utils
from Gat.data import BasicVocab
from Gat.data import FromIterableTextSource
from Gat.data import load_splits
from Gat.data import SentenceGraphDataset
from Gat.data.tokenizers.spacy import WrappedSpacyTokenizer


@pytest.fixture
def sst_dataset() -> SentenceGraphDataset:
    datasets, _, _ = load_splits(
        # Path("data/glue_data/SST-2"),
        Path("actual_data/SST-2_tiny"),
        splits=["train", "dev"],
        lstxt_col=["sentence"],
        sent2graph_name="dep",
        unk_thres=1,
    )
    dataset = datasets["train"]
    return dataset


@pytest.fixture
def glove_vector_for_the() -> torch.Tensor:
    """Currently not used actually."""
    return torch.tensor(
        [
            0.04656,
            0.21318,
            -0.0074364,
            -0.45854,
            -0.035639,
            0.23643,
            -0.28836,
            0.21521,
            -0.13486,
            -1.6413,
            -0.26091,
            0.032434,
            0.056621,
            -0.043296,
            -0.021672,
            0.22476,
            -0.075129,
            -0.067018,
            -0.14247,
            0.038825,
            -0.18951,
            0.29977,
            0.39305,
            0.17887,
            -0.17343,
            -0.21178,
            0.23617,
            -0.063681,
            -0.42318,
            -0.11661,
            0.093754,
            0.17296,
            -0.33073,
            0.49112,
            -0.68995,
            -0.092462,
            0.24742,
            -0.17991,
            0.097908,
            0.083118,
            0.15299,
            -0.27276,
            -0.038934,
            0.54453,
            0.53737,
            0.29105,
            -0.0073514,
            0.04788,
            -0.4076,
            -0.026759,
            0.17919,
            0.010977,
            -0.10963,
            -0.26395,
            0.07399,
            0.26236,
            -0.1508,
            0.34623,
            0.25758,
            0.11971,
            -0.037135,
            -0.071593,
            0.43898,
            -0.040764,
            0.016425,
            -0.4464,
            0.17197,
            0.046246,
            0.058639,
            0.041499,
            0.53948,
            0.52495,
            0.11361,
            -0.048315,
            -0.36385,
            0.18704,
            0.092761,
            -0.11129,
            -0.42085,
            0.13992,
            -0.39338,
            -0.067945,
            0.12188,
            0.16707,
            0.075169,
            -0.015529,
            -0.19499,
            0.19638,
            0.053194,
            0.2517,
            -0.34845,
            -0.10638,
            -0.34692,
            -0.19024,
            -0.2004,
            0.12154,
            -0.29208,
            0.023353,
            -0.11618,
            -0.35768,
            0.062304,
            0.35884,
            0.02906,
            0.0073005,
            0.0049482,
            -0.15048,
            -0.12313,
            0.19337,
            0.12173,
            0.44503,
            0.25147,
            0.10781,
            -0.17716,
            0.038691,
            0.08153,
            0.14667,
            0.063666,
            0.061332,
            -0.075569,
            -0.37724,
            0.01585,
            -0.30342,
            0.28374,
            -0.042013,
            -0.040715,
            -0.15269,
            0.07498,
            0.15577,
            0.10433,
            0.31393,
            0.19309,
            0.19429,
            0.15185,
            -0.10192,
            -0.018785,
            0.20791,
            0.13366,
            0.19038,
            -0.25558,
            0.304,
            -0.01896,
            0.20147,
            -0.4211,
            -0.0075156,
            -0.27977,
            -0.19314,
            0.046204,
            0.19971,
            -0.30207,
            0.25735,
            0.68107,
            -0.19409,
            0.23984,
            0.22493,
            0.65224,
            -0.13561,
            -0.17383,
            -0.048209,
            -0.1186,
            0.0021588,
            -0.019525,
            0.11948,
            0.19346,
            -0.4082,
            -0.082966,
            0.16626,
            -0.10601,
            0.35861,
            0.16922,
            0.07259,
            -0.24803,
            -0.10024,
            -0.52491,
            -0.17745,
            -0.36647,
            0.2618,
            -0.012077,
            0.08319,
            -0.21528,
            0.41045,
            0.29136,
            0.30869,
            0.078864,
            0.32207,
            -0.041023,
            -0.1097,
            -0.092041,
            -0.12339,
            -0.16416,
            0.35382,
            -0.082774,
            0.33171,
            -0.24738,
            -0.048928,
            0.15746,
            0.18988,
            -0.026642,
            0.063315,
            -0.010673,
            0.34089,
            1.4106,
            0.13417,
            0.28191,
            -0.2594,
            0.055267,
            -0.052425,
            -0.25789,
            0.019127,
            -0.022084,
            0.32113,
            0.068818,
            0.51207,
            0.16478,
            -0.20194,
            0.29232,
            0.098575,
            0.013145,
            -0.10652,
            0.1351,
            -0.045332,
            0.20697,
            -0.48425,
            -0.44706,
            0.0033305,
            0.0029264,
            -0.10975,
            -0.23325,
            0.22442,
            -0.10503,
            0.12339,
            0.10978,
            0.048994,
            -0.25157,
            0.40319,
            0.35318,
            0.18651,
            -0.023622,
            -0.12734,
            0.11475,
            0.27359,
            -0.21866,
            0.015794,
            0.81754,
            -0.023792,
            -0.85469,
            -0.16203,
            0.18076,
            0.028014,
            -0.1434,
            0.0013139,
            -0.091735,
            -0.089704,
            0.11105,
            -0.16703,
            0.068377,
            -0.087388,
            -0.039789,
            0.014184,
            0.21187,
            0.28579,
            -0.28797,
            -0.058996,
            -0.032436,
            -0.0047009,
            -0.17052,
            -0.034741,
            -0.11489,
            0.075093,
            0.099526,
            0.048183,
            -0.073775,
            -0.41817,
            0.0041268,
            0.44414,
            -0.16062,
            0.14294,
            -2.2628,
            -0.027347,
            0.81311,
            0.77417,
            -0.25639,
            -0.11576,
            -0.11982,
            -0.21363,
            0.028429,
            0.27261,
            0.031026,
            0.096782,
            0.0067769,
            0.14082,
            -0.013064,
            -0.29686,
            -0.079913,
            0.195,
            0.031549,
            0.28506,
            -0.087461,
            0.0090611,
            -0.20989,
            0.053913,
        ]
    )


@pytest.fixture
def basic_vocab() -> BasicVocab:
    txt_src = FromIterableTextSource(
        [
            (["Love never fails.", "Love overcomes all things."], "yes"),
            (["Guard your heart.", "From his heart, living waters flow."], "no"),
            (["Always be on guard.", "Be watchful."], "yes"),
        ]
    )
    tokenizer = WrappedSpacyTokenizer()
    return BasicVocab(
        txt_src=txt_src,
        tokenizer=tokenizer,
        cache_dir=Path(tempfile.gettempdir()),
        lower_case=True,
        unk_thres=2,
    )


def test_vocab(basic_vocab: BasicVocab) -> None:
    set_id2word = set(basic_vocab._id2word)
    assert len(set_id2word) == len(basic_vocab._id2word)

    expected_setid2word = {
        "[CLS]",
        "[PAD]",
        "[UNK]",
        "guard",
        "love",
        ".",
        "heart",
        "be",
    }
    assert set_id2word == expected_setid2word


def test_draw_svg(sst_dataset: SentenceGraphDataset) -> None:
    example = sst_dataset[0]

    graph = example.lsgraph[0]

    svg_content = graph.to_svg(
        node_namer=lambda node_id: sst_dataset.vocab.get_toks([node_id])[0],
        edge_namer=lambda edge_id: sst_dataset.id2edge_type[edge_id],
    )

    with open("graph.svg", "w") as f:
        f.write(svg_content)


def test_connect_to_cls(sst_dataset: SentenceGraphDataset) -> None:

    dataset = data.ConnectToClsDataset(sst_dataset)

    graph = dataset[0].lsgraph[0]
    svg_content = graph.to_svg(
        node_namer=lambda node_id: dataset.vocab.get_toks([node_id])[0],
        edge_namer=lambda edge_id: dataset.id2edge_type[edge_id],
    )
    with open("graph_with_cls.svg", "w") as f:
        f.write(svg_content)


def test_undirected(sst_dataset: SentenceGraphDataset) -> None:

    dataset = data.UndirectedDataset(sst_dataset)

    graph = dataset[0].lsgraph[0]
    svg_content = graph.to_svg(
        node_namer=lambda node_id: dataset.vocab.get_toks([node_id])[0],
        edge_namer=lambda edge_id: dataset.id2edge_type[edge_id],
    )
    with open("graph_undirected.svg", "w") as f:
        f.write(svg_content)


def test_undirected_connect_to_cls(sst_dataset: SentenceGraphDataset) -> None:

    dataset = data.UndirectedDataset(data.ConnectToClsDataset(sst_dataset))

    graph = dataset[0].lsgraph[0]
    svg_content = graph.to_svg(
        node_namer=lambda node_id: dataset.vocab.get_toks([node_id])[0],
        edge_namer=lambda edge_id: dataset.id2edge_type[edge_id],
    )
    with open("graph_with_cls_undirected.svg", "w") as f:
        f.write(svg_content)
