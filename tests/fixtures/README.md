# Test Fixtures

Checked-in fixtures are synthetic and small.

`native_pose_samples.json` contains synthetic track inputs and numerical output
from the saved native sampler. It covers all ten animated codecs without
bundling game tracks, executable code or research dependencies.

Real game assets should stay outside the repository and be pointed to by
environment variables or ad-hoc comparison scripts.
