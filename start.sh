#!/usr/bin/env bash
set -e

apt-get update -qq
apt-get install -y -q git libsndfile1-dev build-essential python3-dev libportaudio2

cd /workspace/voice-changer/server

pip install numpy==1.23.5
pip install pyworld==0.3.3 --no-build-isolation
pip install -r requirements.txt
pip install --no-deps fairseq
pip install 'omegaconf>=2.1' hydra-core bitarray regex sacrebleu

python3 MMVCServerSIO.py -p 18888 --https true --host 0.0.0.0 --allowed-origins '*'
