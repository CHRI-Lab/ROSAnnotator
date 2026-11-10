#!/bin/sh
set -eu

model_path="/models/${LOCAL_AI_MODEL}.gguf"

if [ ! -f "$model_path" ]; then
    echo "Local model not found: $model_path" >&2
    exit 1
fi

set -- -m "$model_path" "$@"

case "$LOCAL_AI_MODEL" in
    *SmolVLM2-500M-Video-Instruct*|*smolvlm2-500m-video-instruct*)
        mmproj_path="/models/mmproj-SmolVLM2-500M-Video-Instruct-f16.gguf"
        if [ ! -f "$mmproj_path" ]; then
            echo "SmolVLM2 multimodal projector not found: $mmproj_path" >&2
            exit 1
        fi
        set -- "$@" --mmproj "$mmproj_path"
        ;;
esac

exec /app/llama-server "$@"
