#!/usr/bin/env bash
# Rebuild everything from the raw dataset: perceive -> features -> models -> replay -> evidence.
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
py -m saarthi.download
py -m saarthi.prepare
py -m saarthi.features
py -m saarthi.model
py -m saarthi.replay
py -m saarthi.finalize
