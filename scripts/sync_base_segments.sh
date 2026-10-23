#!/bin/bash
# Exchange completed Base pull segments between the Mac (Tenderly workers) and the node
# (local-RPC workers) so neither pulls a segment the other has finished.
MAC=$HOME/Forge/onchain-collusion-evidence/data/raw/base_mac
NODE=cw-sentinel:scratch/collusion/data/base
while true; do
  rsync -a --exclude '*.part' --exclude 'manifest*.jsonl' "$MAC/" "$NODE/" 2>/dev/null
  rsync -a --exclude '*.part' --exclude 'manifest*.jsonl' "$NODE/" "$MAC/" 2>/dev/null
  sleep 120
done
