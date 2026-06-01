# OpenThreatDetection integration

Runtime weapon detection is powered by the [IterateAI/OpenThreatDetection](https://github.com/IterateAI/OpenThreatDetection) model, a **YOLOv4** detector exported as a **TensorFlow SavedModel**. It replaces the legacy Ultralytics YOLO `.pt` weights that previously lived under `weapon_detection/runs/detect/Normal_Compressed/weights/`.

## Layout

```
weapon_detection/openthreat/
├── README.md             # this file
├── weapons.names         # class label list (Gun / Knife / Riffle [sic])
└── savedmodel/           # the TF SavedModel directory
    ├── saved_model.pb
    ├── keras_metadata.pb
    └── variables/
        ├── variables.data-00000-of-00001   # ~244 MB
        └── variables.index
```

The adapter at [api/agents/openthreat_detector.py](../../api/agents/openthreat_detector.py) loads `savedmodel/` via `tf.saved_model.load(...)` and matches the upstream's preprocessing (608×608 BGR, `/255.`) and postprocessing (`tf.image.combined_non_max_suppression`, IOU 0.5).

## Install the SavedModel

The OpenThreatDetection repo doesn't ship a single weight file — it ships the full SavedModel as a directory tree, with the actual weights stored via Git LFS.

### Option A — clone upstream and copy the SavedModel

```sh
brew install git-lfs && git lfs install   # one-time
git clone https://github.com/IterateAI/OpenThreatDetection.git /tmp/OpenThreatDetection
# Verify the LFS variables file is real (~244 MB, not ~130 B):
ls -lh /tmp/OpenThreatDetection/wepapp/weaponresource/checkpoints_weapon/WeaponOct24_608_8K/variables/

# Copy the newer Oct24-8K checkpoint into the project (~256 MB):
cp -R /tmp/OpenThreatDetection/wepapp/weaponresource/checkpoints_weapon/WeaponOct24_608_8K/. \
      $PROJECT_ROOT/weapon_detection/openthreat/savedmodel/
```

There are two checkpoints in the upstream repo: `WeaponOct7_608_6000` and `WeaponOct24_608_8K`. Use the latter — it's later and more iterations. Both are otherwise identically structured.

### Option B — point at a SavedModel you already have

```sh
export OPENTHREAT_WEIGHTS_PATH=/absolute/path/to/your/savedmodel
```

The path must be the **directory** containing `saved_model.pb` (not a file).

## Verify

After installing, restart the backend and check the startup log. You should see:

```
OpenThreatDetector: loaded TF SavedModel from .../weapon_detection/openthreat/savedmodel (classes=['Gun', 'Knife', 'Riffle'])
```

If the log says `OpenThreatDetector: no weapon weights found`, the SavedModel directory is missing or incomplete.

## Performance and timing

CPU YOLOv4 @ 608×608 is ~1–2 s per inference on Apple Silicon. The backend reflects this:

- `WEAPON_DETECT_INTERVAL = 1.5` (seconds between live-stream scans) in [api/main.py](../../api/main.py)
- `WEAPON_DETECT_TIMEOUT = 8` (seconds per scan)
- `WEAPON_CONSECUTIVE_HITS = 2` (hysteresis — alert fires after 2 confirmed scans)

Expect the **first** weapon-alert latency to be ~3–5 seconds end-to-end on CPU. Subsequent inferences are faster because the TF graph is already traced.

## Class labels

The upstream model produces 3 classes:

| Index | Label | Note |
|---|---|---|
| 0 | `Gun` | |
| 1 | `Knife` | |
| 2 | `Riffle` | (upstream's spelling — kept verbatim) |

These labels flow through to the dashboard's weapon-alert banner unchanged.

## Confidence threshold

Upstream's default is `score_weapon = 0.3`. Our pipeline uses `WEAPON_CONF_THRESHOLD = 0.55` for false-positive control. The `conf` parameter is plumbed straight into NMS as `score_threshold`, so anything below 0.55 is dropped before NMS even returns it.

## License

OpenThreatDetection upstream is MIT-licensed.
