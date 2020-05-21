from typing import Iterator
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Tuple

import torch
import torch.nn as nn
from torch import Tensor

from config import GATConfig
from config import GATForSeqClsfConfig
from layers import EmbeddingWrapper
from layers import GATLayerWrapper
from utils import Edge
from utils import EdgeType
from utils import Node
from utils import SentGraph
from utils import sorted_directed


class GATLayered(nn.Module):  # type: ignore
    def __init__(self, config: GATConfig, emb_init: Optional[Tensor]):
        super().__init__()

        do_residual = config.do_residual
        self.emb_wrapper = EmbeddingWrapper(config, emb_init)
        self.lsmid_layer_wrapper = nn.ModuleList(
            [
                GATLayerWrapper(config, do_residual=do_residual)
                for _ in range(config.nmid_layers)
            ]
        )
        self.last_layer = GATLayerWrapper(config, do_residual=False, concat=False)

    def forward(self, tcword_id: Tensor, adj: Tensor) -> Tensor:  # type: ignore
        h = self.emb_wrapper(tcword_id)

        for layer_wrapper in self.lsmid_layer_wrapper:
            h = layer_wrapper(h, adj)

        h = self.last_layer(h, adj)

        return h  # type: ignore


class GATModel(nn.Module):  # type: ignore
    def __init__(self, config: GATConfig, emb_init: Optional[Tensor]):
        super().__init__()
        self.cls_id = config.cls_id
        self.head_to_cls_edge_type = config.nedge_type
        self.undirected = config.undirected
        self.gat_layered = GATLayered(config, emb_init)

    def prepare_batch(
        self, batch: List[SentGraph]
    ) -> Tuple[List[Edge], List[EdgeType], List[List[Node]], List[int]]:
        """
        Increment the relative node numbers in the adjacency list, and the list of key nodes
        """

        lsedge: List[Edge] = []
        lsedge_type: List[EdgeType] = []
        lslsimp_node: List[List[Node]] = []
        nodeid2wordid: List[int] = []

        counter = 0

        for one_lsedge, one_lsedge_type, one_lsimp_node, one_nodeid2wordid in batch:
            # Extend nodeid2wordid
            nodeid2wordid.extend(one_nodeid2wordid)  # type: ignore # None

            # Extend edge index, but increment the numbers
            lsedge.extend(
                [(edge[0] + counter, edge[1] + counter) for edge in one_lsedge]
            )

            # Extend edge type
            lsedge_type.extend(one_lsedge_type)

            # Extend lslshead node as well, but increment the numbers
            lslsimp_node.append([node + counter for node in one_lsimp_node])

            # Increment node counter
            counter += len(one_nodeid2wordid)  # type: ignore

        if self.undirected:
            lsedge = sorted_directed(lsedge)
            lsedge_inv = [(n2, n1) for n1, n2 in lsedge]
            lsedge_type_inv = lsedge_type[:]

            lsedge = lsedge + lsedge_inv
            lsedge_type = lsedge_type + lsedge_type_inv
        return (
            lsedge,
            lsedge_type,
            lslsimp_node,
            nodeid2wordid,
        )


GATForSeqClsfForward = NamedTuple(
    "GATForSeqClsfForward", [("logits", Tensor), ("loss", Optional[Tensor])]
)


class GATForSeqClsf(GATModel):
    def __init__(self, config: GATForSeqClsfConfig, emb_init: Optional[Tensor]) -> None:
        super().__init__(config, emb_init=emb_init)
        nhid = config.nhid
        nclass = config.nclass
        feat_dropout_p = config.feat_dropout_p

        self.linear = nn.Linear(nhid, nclass)
        self.dropout = nn.Dropout(p=feat_dropout_p)
        self.crs_entrpy = nn.CrossEntropyLoss()

    @staticmethod
    def peeled_batch_yielder(batch: List[List[SentGraph]]) -> Iterator[SentGraph]:
        for ex in batch:
            yield ex[0]

    def prepare_batch_for_seq_clsf(
        self, batch: List[List[SentGraph]]
    ) -> Tuple[List[Edge], List[EdgeType], List[List[Node]], List[int]]:
        """
         For each graph in batch
            connect each key node to a new, "CLS" node
            make that "CLS" node the only node in list of key nodes
        do super().prepare_batch()
        """

        # Ensure that we are processing only one sentgraph per example
        assert set(map(len, batch)) == {1}

        # Connect all the "head nodes" to a new [CLS] node
        new_batch: List[SentGraph] = []
        for (
            one_lsedge,
            one_lsedge_type,
            one_lsimp_node,
            one_nodeid2wordid,
        ) in self.peeled_batch_yielder(batch):
            assert one_nodeid2wordid is not None
            assert self.cls_id not in one_nodeid2wordid
            new_nodeid2wordid = one_nodeid2wordid + [self.cls_id]

            new_cls_node = len(new_nodeid2wordid) - 1
            lshead_to_cls_edge = [(node, new_cls_node) for node in one_lsimp_node]
            lshead_to_cls_edge_type = [
                self.head_to_cls_edge_type for _ in one_lsimp_node
            ]
            new_lsedge = one_lsedge + lshead_to_cls_edge
            new_lsedge_type = one_lsedge_type + lshead_to_cls_edge_type

            new_lsimp_node = [new_cls_node]

            new_batch.append(
                SentGraph(
                    lsedge=new_lsedge,
                    lsedge_type=new_lsedge_type,
                    lsimp_node=new_lsimp_node,
                    nodeid2wordid=new_nodeid2wordid,
                )
            )

        return self.prepare_batch(new_batch)

    def forward(self, X: List[List[SentGraph]], y: Optional[List[int]]) -> GATForSeqClsfForward:  # type: ignore
        """

        Returns
        -------
        """

        new_X = self.prepare_batch_for_seq_clsf(X)
        lsedge, lsedge_type, lslsimp_node, nodeid2wordid = new_X
        # "unpack" lscls_node ,since per batch, we're only looking at output of CLS token
        assert set(map(len, lslsimp_node)) == {1}
        lscls_node = [lsimp_node[0] for lsimp_node in lslsimp_node]

        # Device
        device = next(self.parameters()).device

        word_ids = torch.tensor(nodeid2wordid, device=device)

        N = len(nodeid2wordid)
        adj: torch.Tensor = torch.zeros(N, N, dtype=torch.float, device=device)
        adj[list(zip(*lsedge))] = 1

        h = self.gat_layered(word_ids, adj)

        cls_id_h = h[lscls_node]

        cls_id_h = self.dropout(cls_id_h)
        logits = self.linear(cls_id_h)

        loss = None
        if y is not None:
            new_y = torch.tensor(y, device=device)
            loss = self.crs_entrpy(logits, new_y)

        return GATForSeqClsfForward(logits, loss)
