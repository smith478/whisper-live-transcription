import asyncio
from typing import Tuple

import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, Request
from faster_whisper import WhisperModel

app = FastAPI()

MODEL_TYPE = "large-v3"
RUN_TYPE = "cpu"  # "cpu" or "gpu"

# For CPU usage (https://github.com/SYSTRAN/faster-whisper/issues/100#issuecomment-1492141352)
NUM_WORKERS = 10
CPU_THREADS = 4

# For GPU usage
GPU_DEVICE_INDICES = [0]

VAD_FILTER = True


def create_whisper_model() -> WhisperModel:
    if RUN_TYPE.lower() == "gpu":
        whisper = WhisperModel(MODEL_TYPE,
                               device="cuda",
                               compute_type="float16",
                               device_index=GPU_DEVICE_INDICES,
                               download_root="./models")
    elif RUN_TYPE.lower() == "cpu":
        whisper = WhisperModel(MODEL_TYPE,
                               device="cpu",
                               compute_type="int8",
                               num_workers=NUM_WORKERS,
                               cpu_threads=CPU_THREADS,
                               download_root="./models")
    else:
        raise ValueError(f"Invalid model type: {RUN_TYPE}")

    print("Loaded model")

    return whisper


model = create_whisper_model()
print("Loaded model")


async def parse_body(request: Request):
    data: bytes = await request.body()
    return data


def execute_blocking_whisper_prediction(
        model: WhisperModel,
        audio_data_array: np.ndarray,
        language_code: str = "") -> Tuple[str, str, float]:
    language_code = language_code.lower().strip()
    segments, info = model.transcribe(
        audio_data_array,
        language=language_code if language_code != "" else None,
        beam_size=5,
        vad_filter=VAD_FILTER,
        vad_parameters=dict(min_silence_duration_ms=500))
    segments = [s.text for s in segments]
    transcription = " ".join(segments)
    transcription = transcription.strip()
    return transcription, info.language, info.language_probability


@app.post("/predict")
async def predict(
        audio_data: bytes = Depends(parse_body), language_code: str = ""):
    # Convert the audio bytes to a NumPy array
    audio_data_array: np.ndarray = np.frombuffer(audio_data, np.int16).astype(
        np.float32) / 255.0

    try:
        # Run the prediction on the audio data
        result = await asyncio.get_running_loop().run_in_executor(
            None, execute_blocking_whisper_prediction, model, audio_data_array,
            language_code)

    except Exception as e:
        print(e)
        result = "Error"

    return {
        "prediction": result[0],
        "language": result[1],
        "language_probability": result[2]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)
