#!/usr/bin/env node
/**
 * 0G Storage bridge for Python SDK.
 *
 * Called by ogmem/storage.py via subprocess.
 * Prints a single JSON line to stdout.
 *
 * Usage:
 *   node scripts/zg_storage.js upload   <private_key> <indexer_url> <rpc_url> <hex_data>
 *   node scripts/zg_storage.js download <private_key> <indexer_url> <rpc_url> <root_hash>
 */

// XMLHttpRequest polyfill required by open-jsonrpc-provider (used by 0g-ts-sdk)
global.XMLHttpRequest = require('xhr2');

const {
  Indexer,
  MemData,
} = require('@0gfoundation/0g-ts-sdk');

const { ethers } = require('ethers');

const [,, command, privateKey, indexerUrl, rpcUrl, data] = process.argv;

function ok(result) {
  process.stdout.write(JSON.stringify({ ok: true, ...result }) + '\n');
  process.exit(0);
}

function fail(msg) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(msg) }) + '\n');
  process.exit(1);
}

async function upload() {
  try {
    const provider = new ethers.JsonRpcProvider(rpcUrl);
    const signer = new ethers.Wallet(privateKey, provider);
    const indexer = new Indexer(indexerUrl);

    // data is hex-encoded bytes
    const buf = Buffer.from(data, 'hex');
    const memData = new MemData(buf);

    const [tree, treeErr] = await memData.merkleTree();
    if (treeErr) throw new Error('merkleTree: ' + treeErr);
    const rootHash = tree.rootHash();

    // 0G Chain requires min 2 Gwei gas tip; set 4 Gwei to be safe
    const uploadOpts = { tags: '0x', finalityRequired: true, taskSize: 1, expectedReplica: 1, skipTx: false, fee: 0n };
    const nodeOpts = { gasPrice: BigInt('4000000000') };
    const [result, uploadErr] = await indexer.upload(memData, rpcUrl, signer, uploadOpts, undefined, nodeOpts);
    if (uploadErr) throw new Error('upload: ' + uploadErr);

    ok({ root_hash: rootHash, tx_hash: result?.txHash || '' });
  } catch (e) {
    fail(e.message || e);
  }
}

async function download() {
  try {
    const indexer = new Indexer(indexerUrl);
    const root = data.startsWith('0x') ? data : '0x' + data;

    const tmpFile = '/tmp/zg_dl_' + Date.now();
    const dlErr = await indexer.download(root, tmpFile, false);
    if (dlErr) throw new Error('download: ' + dlErr);

    const fs = require('fs');
    const raw = fs.readFileSync(tmpFile);
    fs.unlinkSync(tmpFile);
    ok({ data: raw.toString('hex') });
  } catch (e) {
    fail(e.message || e);
  }
}

if (command === 'upload') upload();
else if (command === 'download') download();
else fail('Unknown command: ' + command);
