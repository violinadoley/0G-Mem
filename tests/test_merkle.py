"""Tests for Merkle tree and proof generation."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ogmem.merkle import MerkleTree, MerkleProof


def test_empty_tree_has_stable_root():
    tree = MerkleTree()
    root1 = tree.get_root()
    root2 = tree.get_root()
    assert root1 == root2


def test_single_leaf():
    tree = MerkleTree()
    tree.add_leaf("blob_abc123")
    root = tree.get_root()
    assert isinstance(root, str)
    assert len(root) == 64  # SHA-256 hex


def test_root_changes_on_add():
    tree = MerkleTree()
    tree.add_leaf("blob_1")
    root1 = tree.get_root()
    tree.add_leaf("blob_2")
    root2 = tree.get_root()
    assert root1 != root2


def test_proof_generation_and_verification():
    tree = MerkleTree()
    blob_ids = ["blob_a", "blob_b", "blob_c", "blob_d"]
    for b in blob_ids:
        tree.add_leaf(b)

    for blob_id in blob_ids:
        proof = tree.get_proof(blob_id)
        assert MerkleTree.verify(proof), f"Proof for {blob_id} failed verification"


def test_proof_fails_for_wrong_root():
    tree = MerkleTree()
    tree.add_leaf("blob_x")
    tree.add_leaf("blob_y")
    proof = tree.get_proof("blob_x")

    # Tamper with the root
    tampered = MerkleProof(
        leaf=proof.leaf,
        siblings=proof.siblings,
        directions=proof.directions,
        root="deadbeef" * 8,
    )
    assert not MerkleTree.verify(tampered)


def test_proof_fails_for_unknown_blob():
    tree = MerkleTree()
    tree.add_leaf("blob_real")

    with pytest.raises(ValueError):
        tree.get_proof("blob_fake")


def test_odd_number_of_leaves():
    tree = MerkleTree()
    for i in range(5):  # odd
        tree.add_leaf(f"blob_{i}")

    # All proofs should still be valid
    for i in range(5):
        proof = tree.get_proof(f"blob_{i}")
        assert MerkleTree.verify(proof)


def test_serialization_roundtrip():
    tree = MerkleTree()
    tree.add_leaf("blob_serialize_test")
    tree.add_leaf("blob_another")

    data = tree.to_dict()
    restored = MerkleTree.from_dict(data)

    assert tree.get_root() == restored.get_root()


def test_deterministic_root():
    """Same blobs in same order must always produce same root."""
    tree1 = MerkleTree()
    tree2 = MerkleTree()

    blobs = ["a", "b", "c", "d", "e"]
    for b in blobs:
        tree1.add_leaf(b)
        tree2.add_leaf(b)

    assert tree1.get_root() == tree2.get_root()
