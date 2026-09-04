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