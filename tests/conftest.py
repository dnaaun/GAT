"""PyTest fixtures that are shared across tests files.

https://docs.pytest.org/en/stable/fixture.html#conftest-py-sharing-fixture-functions

    "If during implementing your tests you realize that you want to use a fixture
     function from multiple test files you can move it to a conftest.py file. You don’t
     need to import the fixture you want to use in a test, it automatically gets
     discovered by pytest. The discovery of fixture functions starts at test classes,
     then test modules, then conftest.py files and finally builtin and third party
     plugins."

"""
from __future__ import annotations

import shutil
import tempfile
import typing as T
from pathlib import Path

import pytest
import torch

from Gat import data
from Gat.neural import layers


@pytest.fixture(scope="session")
def device() -> torch.device:
    # This was stolen from private torch code
    if hasattr(torch._C, "_cuda_isDriverSufficient") and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


@pytest.fixture(scope="session")
def temp_dir() -> T.Iterator[Path]:
    """A temporary directory."""
    dir_ = Path(tempfile.mkdtemp("gat_testing"))
    yield dir_
    shutil.rmtree(dir_)


class VocabSetup(T.NamedTuple):
    basic_vocab: data.BasicVocab
    bert_vocab: data.BertVocab


@pytest.fixture(scope="session")
def vocab_setup(temp_dir: Path) -> VocabSetup:
    txt_src = data.FromIterableTextSource(
        [(["guard your heart"], "yes"), (["pacification"], "no")]
    )

    basic_vocab = data.BasicVocab(
        txt_src=txt_src,
        tokenizer=data.tokenizers.spacy.WrappedSpacyTokenizer(),
        cache_dir=temp_dir,
        unk_thres=1,
    )

    bert_vocab = data.BertVocab(
        txt_src=txt_src,
        tokenizer=data.tokenizers.bert.WrappedBertTokenizer(),
        cache_dir=temp_dir,
    )

    return VocabSetup(basic_vocab=basic_vocab, bert_vocab=bert_vocab)


@pytest.fixture(scope="session")
def bert_embedder(vocab_setup: VocabSetup) -> layers.BertEmbedder:
    embedder = layers.BertEmbedder(vocab=vocab_setup.bert_vocab)
    return embedder


@pytest.fixture(scope="session")
def reconciler_embedder(
    vocab_setup: VocabSetup, bert_embedder: layers.BertEmbedder
) -> layers.ReconcilingEmbedder:
    embedder = layers.ReconcilingEmbedder(
        vocab_setup.bert_vocab, vocab_setup.basic_vocab, bert_embedder
    )
    return embedder