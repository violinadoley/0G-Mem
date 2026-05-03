"""
Merkle tree implementation for 0G Mem.
Provides inclusion proofs: prove that a blob_id was in memory at a given root.
"""

import hashlib
from dataclasses import dataclass


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def sha256_pair(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode()).hexdigest()


@dataclass
class MerkleProof:
    leaf: str           # blob_id being proven
    siblings: list[str] # sibling hashes at each level (bottom to top)
    directions: list[int]  # 0 = sibling is on right, 1 = sibling is on left
    root: str           # expected Merkle root


class MerkleTree:
    """Mutable SHA-256 Merkle tree with inclusion proof generation and verification."""

    def __init__(self):
        self._leaves: list[str] = []  # ordered list of blob_ids

    def add_leaf(self, blob_id: str):
        self._leaves.append(sha256(blob_id))

    def get_root(self) -> str:
        if not self._leaves:
            return sha256("empty")
        return self._compute_root(self._leaves)

    def get_proof(self, blob_id: str) -> MerkleProof:
        """Generate an inclusion proof. Raises ValueError if blob_id is not in the tree."""
        leaf_hash = sha256(blob_id)
        if leaf_hash not in self._leaves:
            raise ValueError(f"blob_id {blob_id!r} not found in tree")

        index = self._leaves.index(leaf_hash)
        proof = self._compute_proof(self._leaves, index)
        return MerkleProof(
            leaf=blob_id,
            siblings=proof["siblings"],
            directions=proof["directions"],
            root=self.get_root(),
        )

    @staticmethod
    def verify(proof: MerkleProof) -> bool:
        """Stateless proof verification. Returns True if the proof is valid."""
        current = sha256(proof.leaf)
        for sibling, direction in zip(proof.siblings, proof.directions):
            if direction == 0:
                # sibling is on the right
                current = sha256_pair(current, sibling)
            else:
                # sibling is on the left
                current = sha256_pair(sibling, current)
        return current == proof.root

    def _compute_root(self, layer: list[str]) -> str:
        if len(layer) == 1:
            return layer[0]
        next_layer = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left  # duplicate last if odd
            next_layer.append(sha256_pair(left, right))
        return self._compute_root(next_layer)

    def _compute_proof(self, layer: list[str], index: int) -> dict:
        siblings = []
        directions = []
        while len(layer) > 1:
            next_layer = []
            for i in range(0, len(layer), 2):
                left = layer[i]
                right = layer[i + 1] if i + 1 < len(layer) else left
                next_layer.append(sha256_pair(left, right))

            if index % 2 == 0:
                sibling_index = index + 1 if index + 1 < len(layer) else index
                siblings.append(layer[sibling_index])
                directions.append(0)
            else:
                siblings.append(layer[index - 1])
                directions.append(1)

            index = index // 2
            layer = next_layer

        return {"siblings": siblings, "directions": directions}

    def to_dict(self) -> dict:
        """Serialize tree state for persistence."""
        return {"leaves": self._leaves, "root": self.get_root()}

    @classmethod
    def from_dict(cls, data: dict) -> "MerkleTree":
        """Restore tree state from serialized form."""
        tree = cls()
        tree._leaves = data["leaves"]
        return tree
