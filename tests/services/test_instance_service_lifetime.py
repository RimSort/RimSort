"""Regression tests for the InstanceService lifetime bug (#2188 discussion).

InstanceService is a plain Python class that connects its slots to EventBus
signals in ``__init__``. PySide6 does not keep bound-method receivers alive,
so if the constructing code drops the only reference the service is garbage
collected and every instance action (backup/restore/clone/create/delete)
silently does nothing -- no dialog, no log line, no error.
"""

import gc
import weakref
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from app.controllers.app_controller import AppController
from app.services.instance_service import InstanceService
from app.utils.event_bus import EventBus


def test_instance_service_survives_without_external_reference(
    qapp: QApplication,
) -> None:
    """Constructing the service with no retained reference kills its slots."""
    service = InstanceService(settings=MagicMock(), steamcmd_wrapper=MagicMock())
    ref = weakref.ref(service)
    del service
    gc.collect()

    assert ref() is None, (
        "InstanceService was garbage collected; bound-method slots on "
        "EventBus are dead. Callers must retain a strong reference."
    )


def test_create_new_instance_slot_receives_event(qapp: QApplication) -> None:
    """Emitting do_create_new_instance must reach the service slot.

    The class attribute is patched *before* construction because Qt captures
    the bound method at connect time; rebinding the instance attribute
    afterwards would not be observed.
    """
    with patch.object(InstanceService, "create_new_instance") as slot:
        InstanceService(settings=MagicMock(), steamcmd_wrapper=MagicMock())
        EventBus().do_create_new_instance.emit()

    assert slot.called, "EventBus.do_create_new_instance did not reach the slot"


def test_all_instance_actions_are_connected(qapp: QApplication) -> None:
    """Every instance signal must reach its corresponding service slot."""
    for signal_name, method_name, args in (
        ("do_backup_existing_instance", "backup_existing_instance", ("Default",)),
        ("do_clone_existing_instance", "clone_existing_instance", ("Default",)),
        ("do_create_new_instance", "create_new_instance", ()),
        ("do_delete_current_instance", "delete_current_instance", ()),
        ("do_restore_instance_from_archive", "restore_instance_from_archive", ()),
    ):
        with patch.object(InstanceService, method_name) as slot:
            InstanceService(settings=MagicMock(), steamcmd_wrapper=MagicMock())
            getattr(EventBus(), signal_name).emit(*args)
            assert slot.called, f"{signal_name} has no live receiver on the service"


def test_app_controller_retains_instance_service(qapp: QApplication) -> None:
    """AppController must keep a strong reference to the instance service."""
    controller = AppController.__new__(AppController)
    controller.settings_controller = MagicMock()
    controller.steamcmd_wrapper = MagicMock()

    controller.initialize_instance_service()

    service = getattr(controller, "instance_service", None)
    assert isinstance(service, InstanceService), (
        "AppController discarded the InstanceService; instance actions are dead"
    )
