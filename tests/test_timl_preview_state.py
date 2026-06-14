from __future__ import annotations

import unittest

from blender_adapter.timl_preview_state import diff_sampled_transforms_from_imported_signature
from blender_adapter.timl_preview_state import imported_preview_signature_json


class _ImportedKeyframe:
    def __init__(self, *, frame: float, value, interpolation: int):
        self.frame = float(frame)
        self.value = tuple(float(component) for component in value)
        self.interpolation = int(interpolation)


class _ImportedTransform:
    def __init__(self, *, type_index: int, transform_index: int, data_type: int, keyframes):
        self.type_index = int(type_index)
        self.transform_index = int(transform_index)
        self.data_type = int(data_type)
        self.keyframes = tuple(keyframes)


class _SampledKeyframe:
    def __init__(self, *, frame: float, value, interpolation: str):
        self.frame = float(frame)
        self.value = tuple(float(component) for component in value)
        self.interpolation = str(interpolation)


class _SampledTransform:
    def __init__(self, *, type_index: int, transform_index: int, data_type: int, keyframes):
        self.type_index = int(type_index)
        self.transform_index = int(transform_index)
        self.data_type = int(data_type)
        self.keyframes = tuple(keyframes)


class TimlPreviewStateTests(unittest.TestCase):
    def test_advanced_source_preview_counts_as_unchanged_when_sampled_preview_matches(self):
        raw_signature = imported_preview_signature_json(
            [
                _ImportedTransform(
                    type_index=0,
                    transform_index=0,
                    data_type=2,
                    keyframes=(
                        _ImportedKeyframe(frame=0.0, value=(1.0,), interpolation=3),
                        _ImportedKeyframe(frame=10.0, value=(2.0,), interpolation=3),
                    ),
                )
            ]
        )

        diff = diff_sampled_transforms_from_imported_signature(
            raw_signature,
            (
                _SampledTransform(
                    type_index=0,
                    transform_index=0,
                    data_type=2,
                    keyframes=(
                        _SampledKeyframe(frame=0.0, value=(1.0,), interpolation="LINEAR"),
                        _SampledKeyframe(frame=10.0, value=(2.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        self.assertTrue(diff.available)
        self.assertTrue(diff.is_exact_match)
        self.assertEqual(diff.changed_identities, ())
        self.assertEqual(diff.missing_identities, ())
        self.assertEqual(diff.extra_identities, ())

    def test_value_change_is_reported_as_changed_identity(self):
        raw_signature = imported_preview_signature_json(
            [
                _ImportedTransform(
                    type_index=0,
                    transform_index=1,
                    data_type=1,
                    keyframes=(
                        _ImportedKeyframe(frame=5.0, value=(7.0,), interpolation=1),
                    ),
                )
            ]
        )

        diff = diff_sampled_transforms_from_imported_signature(
            raw_signature,
            (
                _SampledTransform(
                    type_index=0,
                    transform_index=1,
                    data_type=1,
                    keyframes=(
                        _SampledKeyframe(frame=5.0, value=(9.0,), interpolation="LINEAR"),
                    ),
                ),
            ),
        )

        self.assertTrue(diff.available)
        self.assertEqual(diff.changed_identities, ((0, 1),))
        self.assertFalse(diff.is_exact_match)


if __name__ == "__main__":
    unittest.main()
