"""Tests for layers.

PyTest is useful. But it's not intuitive at all. Please check out how PyTest works
first.
"""
from __future__ import annotations

import tempfile
import typing as T
from pathlib import Path

import pytest
import torch
from torch import nn
from tqdm import tqdm  # type: ignore

from Gat.neural import layers
from tests.conftest import GatSetup


@pytest.fixture(scope="session")
def temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="GAT_test"))


def test_best_num_heads(gat_setup: GatSetup, device: torch.device) -> None:

    if not device == torch.device("cuda"):
        lsnum_heads = [4, 12]
    else:
        lsnum_heads = [2, 4, 12, 64, 384]

    crs_entrpy = nn.CrossEntropyLoss()
    n_steps = 5000

    steps_to_converge_for_num_heads: T.Dict[int, int] = {}
    for num_heads in lsnum_heads:
        head_size = gat_setup.all_config.model.embed_dim // num_heads
        # Edge features are dependent on head size
        key_edge_features: torch.FloatTensor = torch.randn(  # type: ignore
            gat_setup.all_config.trainer.train_batch_size,
            gat_setup.seq_length,
            gat_setup.seq_length,
            head_size,
            names=("B", "N_left", "N_right", "head_size"),
            requires_grad=True,
            device=device,
        )

        multihead_att = layers.GraphMultiHeadAttention(
            embed_dim=gat_setup.all_config.model.embed_dim,
            num_heads=num_heads,
            edge_dropout_p=0.3,
        )
        multihead_att.to(device)
        adam = torch.optim.Adam(
            # Include key_edge_features in features to be optimized
            [key_edge_features]
            + T.cast(T.List[torch.FloatTensor], list(multihead_att.parameters())),
            lr=1e-3,
        )
        multihead_att.train()
        for step in tqdm(range(1, n_steps + 1), desc=f"num_heads={num_heads}"):
            after_self_att = multihead_att(
                adj=gat_setup.adj,
                node_features=gat_setup.node_features,
                key_edge_features=key_edge_features,
            )
            loss = crs_entrpy(
                after_self_att.flatten(["B", "N"], "BN").rename(None),
                gat_setup.node_labels.flatten(["B", "N"], "BN").rename(None),
            )
            preds = after_self_att.rename(None).argmax(dim=-1)
            if torch.all(torch.eq(preds, gat_setup.node_labels)):
                steps_to_converge_for_num_heads[num_heads] = step
                break
            loss.backward()
            adam.step()
        if not torch.all(torch.eq(preds, gat_setup.node_labels)):
            print(f"Did not converge for num_heads={num_heads}")
    print(
        "converged for heads: "
        + " | ".join(
            f"num_heads: {num_heads}, step: {steps}"
            for num_heads, steps in steps_to_converge_for_num_heads.items()
        )
    )
