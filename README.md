# rnk-agent

API used for this project:

| Method | Path                    | Description                                                  |
|--------|-------------------------|---------------------------------------------------------------|
| POST   | `/rnk/schedule`         | Enqueue a command: `{"move": <cm>}` or `{"rotate": <deg>}`    |
| GET    | `/rnk/schedule`         | Inspect the queue (running + pending commands)                |
| POST   | `/rnk/stop`             | Halt the motors immediately and clear the queue                |
| POST   | `/rnk/camera/ptz/absolute` | Move the camera to an absolute pan/tilt/zoom position       |
| POST   | `/rnk/camera/ptz/relative` | Move the camera by a pan/tilt/zoom delta                    |
| POST   | `/rnk/camera/ptz/stop`  | Stop any in-progress camera movement                           |
| POST   | `/rnk/camera/home`      | Reset the camera to its home/center position                   |
| GET    | `/rnk/camera/status`    | Current camera PTZ position + capabilities                     |
| GET    | `/rnk/camera/snapshot`  | Capture a single JPEG frame from the camera's RTSP stream       |

Commands are executed **strictly one by one**, in the order received, by a
single worker thread. After every command the motors are stopped, so the
platform is never left moving on its own.

For move command: <cm> can be positive and negative

For rotate command: degrees can be positive and negative

Temporary limitation: NEVER call stop command as it locks robot down until reboot

Absoulte PTZ payload: {"pan": 0.5, "tilt": -0.2, "zoom": 0.3}. zoom is optional (does not work for current camera)

Relative PTZ payload format is the same, but the values are relative.

Home command: empty payload

Status sample response:
```json
{
  "pan": 0.5,
  "tilt": -0.2,
  "zoom": 0.3,
  "moving": false,
  "capabilities": {"absolute": true, "relative": true, "home": true}
}
```

/rnk/camera/snapshot?scaled=true returns low res snapshot (640x480)
/rnk/camera/snapshot returns full scale snapshot (1920x1080)

Server IP for now is 192.168.1.20. It should be stored in config.

## Voice input (speech -> text -> agent)

The agent continuously receives raw microphone audio streamed by rnk-rpi
over a plain TCP socket (`audio_stream` in `config.yaml`, matching
rnk-rpi's `app/audio/capture_constants.py`), independent of the
perceive/decide/act loop above:

1. `rnk_agent.audio_stream_client.AudioStreamClient` connects to the Pi and
   reconnects automatically if the connection drops (connection status is
   printed, e.g. `[audio] connected to ...` / `[audio] could not connect...`).
2. `rnk_agent.speech_segmenter.SpeechSegmenter` runs a VAD (`webrtcvad`)
   over the incoming audio with a bounded pre-roll buffer: speech "starts"
   once enough consecutive frames look like speech (keeping the pre-roll so
   the utterance isn't clipped), and only "ends" after enough consecutive
   silence — a short pause mid-sentence doesn't cut it short.
3. Finalized utterances are transcribed locally by
   `rnk_agent.stt.WhisperSTT` (faster-whisper; see `stt.model_size` /
   `stt.language` in `config.yaml` — defaults to a multilingual model with
   Russian).
4. The resulting text is pushed into the same `MicrophoneInputChannel` used
   for typed stdin input, so it shows up to the model as something
   "overheard" on its next step exactly like typed lines do.

This whole pipeline (`rnk_agent.speech_pipeline.SpeechPipeline`) runs on
background threads and is independent of `agent_loop`'s iteration cadence,
so an utterance spanning multiple loop iterations is still captured and
transcribed correctly — only finished utterances are ever emitted.

STT/VAD engines are behind small interfaces (`SpeechToText` in `stt.py`,
`AudioSource` on the rnk-rpi side) so they can be swapped out later without
touching the rest of the pipeline.