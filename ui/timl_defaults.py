"""Blender-free defaults for raw TIML authoring dialogs."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_TIML_HASH_HEX = "0x00000000"


@dataclass(frozen=True)
class TimlAddTypeDefaults:
    type_index: int
    timeline_hash_hex: str
    datatype_hash_hex: str
    data_type_key: str


@dataclass(frozen=True)
class TimlAddTransformDefaults:
    type_index: int
    transform_index: int
    timeline_hash_hex: str
    datatype_hash_hex: str
    data_type_key: str


def _text_attr(item, name: str) -> str:
    return str(getattr(item, name, "") or "")


def _int_attr(item, name: str, *, default: int = 0) -> int:
    try:
        return int(getattr(item, name, default))
    except (TypeError, ValueError):
        return int(default)


def data_type_key_for_name(name: str, *, items, fallback: str = "1") -> str:
    for item_key, label, _description in items:
        if str(label) == str(name):
            return str(item_key)
    return str(fallback)


def next_available_type_index(bindings: list[dict[str, object]]) -> int:
    if not bindings:
        return 0
    return max(int(binding["type_index"]) for binding in bindings) + 1


def next_available_transform_index(bindings: list[dict[str, object]], type_index: int) -> int:
    matching = [
        int(binding["transform_index"])
        for binding in bindings
        if int(binding["type_index"]) == int(type_index)
    ]
    if not matching:
        return 0
    return max(matching) + 1


def seed_add_timl_type_defaults(
    bindings: list[dict[str, object]],
    *,
    selected_block=None,
    selected_transform=None,
    data_type_items=(),
    fallback_data_type_key: str = "1",
) -> TimlAddTypeDefaults:
    timeline_hash_hex = (
        _text_attr(selected_block, "raw_timeline_label")
        or _text_attr(selected_transform, "raw_timeline_display")
        or DEFAULT_TIML_HASH_HEX
    )
    datatype_hash_hex = _text_attr(selected_transform, "raw_datatype_display") or DEFAULT_TIML_HASH_HEX
    data_type_key = data_type_key_for_name(
        _text_attr(selected_transform, "data_type_name"),
        items=data_type_items,
        fallback=fallback_data_type_key,
    )
    return TimlAddTypeDefaults(
        type_index=next_available_type_index(bindings),
        timeline_hash_hex=timeline_hash_hex,
        datatype_hash_hex=datatype_hash_hex,
        data_type_key=data_type_key,
    )


def seed_add_timl_transform_defaults(
    bindings: list[dict[str, object]],
    *,
    selected_block=None,
    selected_transform=None,
    data_type_items=(),
    fallback_data_type_key: str = "1",
) -> TimlAddTransformDefaults:
    if selected_transform is not None:
        type_index = _int_attr(selected_transform, "type_index", default=0)
        return TimlAddTransformDefaults(
            type_index=type_index,
            transform_index=next_available_transform_index(bindings, type_index),
            timeline_hash_hex=_text_attr(selected_transform, "raw_timeline_display") or DEFAULT_TIML_HASH_HEX,
            datatype_hash_hex=_text_attr(selected_transform, "raw_datatype_display") or DEFAULT_TIML_HASH_HEX,
            data_type_key=data_type_key_for_name(
                _text_attr(selected_transform, "data_type_name"),
                items=data_type_items,
                fallback=fallback_data_type_key,
            ),
        )

    if selected_block is not None:
        type_index = _int_attr(selected_block, "type_index", default=next_available_type_index(bindings))
        return TimlAddTransformDefaults(
            type_index=type_index,
            transform_index=next_available_transform_index(bindings, type_index),
            timeline_hash_hex=_text_attr(selected_block, "raw_timeline_label") or DEFAULT_TIML_HASH_HEX,
            datatype_hash_hex=DEFAULT_TIML_HASH_HEX,
            data_type_key=str(fallback_data_type_key),
        )

    type_index = next_available_type_index(bindings)
    return TimlAddTransformDefaults(
        type_index=type_index,
        transform_index=0,
        timeline_hash_hex=DEFAULT_TIML_HASH_HEX,
        datatype_hash_hex=DEFAULT_TIML_HASH_HEX,
        data_type_key=str(fallback_data_type_key),
    )
