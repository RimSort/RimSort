from typing import Any, Iterable


def recursively_update_dict(
    a_dict: dict[str, Any],
    b_dict: dict[str, Any],
    prune_exceptions: Iterable[str] = (),
    purge_keys: Iterable[str] = (),
    recurse_exceptions: Iterable[str] = (),
) -> None:
    """Recursively update dict *a_dict* in-place with values from *b_dict*.

    - Keys in ``recurse_exceptions`` are overwritten directly (not merged).
    - Keys in ``a_dict`` that are in ``recurse_exceptions`` but missing from ``b_dict`` are deleted.
    - Empty sub-dicts are pruned unless their key is in ``prune_exceptions``.
    - Keys listed in ``purge_keys`` are unconditionally removed from ``a_dict``.
    """
    # recurse_exceptions keys present in b_dict overwrite a_dict (lines below).
    # Keys absent from b_dict are left alone — absence means "no new data",
    # not "delete existing data".
    for key, value in b_dict.items():
        if recurse_exceptions and key in recurse_exceptions:
            a_dict[key] = value
        elif (
            key in a_dict and isinstance(a_dict[key], dict) and isinstance(value, dict)
        ):
            recursively_update_dict(
                a_dict[key],
                value,
                prune_exceptions=prune_exceptions,
                purge_keys=purge_keys,
                recurse_exceptions=recurse_exceptions,
            )
        else:
            a_dict[key] = value
    keys_to_delete = [
        key
        for key, value in a_dict.items()
        if isinstance(value, dict) and not value and key not in prune_exceptions
    ]
    for key in keys_to_delete:
        del a_dict[key]
    for key in purge_keys:
        if key in a_dict:
            del a_dict[key]
