# xrobot-vr-stream

Host-level XRoboToolkit input service shared by robot projects. It is the only
XRoboToolkit SDK client and publishes complete, versioned VR frames on ZMQ port
`5592`. Robot projects subscribe to the stream and do not start XRoboToolkit.
The service extra builds `xrobottoolkit-sdk` non-editably from a sibling SDK
checkout into this project's dedicated `.venv`.

## Install

The service installation expects this source layout:

```text
workspace/
├── xrobot_vr_stream/
└── vr/
    └── XRoboToolkit-PC-Service-Pybind/
```

The SDK checkout must provide its Python package metadata and the atomic
`get_body_state()` binding used by the publisher. Then install the dedicated
service environment:

```bash
cd workspace/xrobot_vr_stream
uv sync --extra service --no-editable
bash scripts/manage_service.sh install
```

Set `XROBOTOOLKIT_PC_SERVICE_DIR` if the PC service is not installed at
`/opt/apps/roboticsservice`.

## Service

After this one-time installation, subscribers to the default local endpoint
automatically start `xrobot-vr-input.service`, which also starts the PC service.
Manual diagnostics remain available through `health`, `status`, and `logs`:

```bash
bash scripts/manage_service.sh health
bash scripts/manage_service.sh status
bash scripts/manage_service.sh logs
```

Use `enable` for automatic startup with the systemd user session. The installed
units are `xrobotoolkit-pc.service` and `xrobot-vr-input.service`.

The dedicated environment is intentional: the host-level service remains
available when a robot project recreates or changes its own environment.

For a no-headset protocol smoke test, stop the live service first and run:

```bash
.venv/bin/xrobot-vr-publisher --source synthetic
```

## Client

```python
from xrobot_vr_stream import VrSubscriber

subscriber = VrSubscriber(connect="tcp://127.0.0.1:5592")
subscriber.start()
frame = subscriber.poll()
```

The protocol publishes raw XR input and coordinate/convention metadata. Button
meaning, robot retargeting, SMPL conversion, and policy control belong to each
consumer project.
