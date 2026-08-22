from pytestqt.qtbot import QtBot

from app.models.animations import LoadingAnimation, WorkThread


def test_work_thread_exception() -> None:
    """Test that WorkThread captures exceptions thrown by the target."""
    def failing_target() -> None:
        raise ValueError("test error")
    
    thread = WorkThread(target=failing_target)
    thread.run()
    assert isinstance(thread.exception, ValueError)
    assert str(thread.exception) == "test error"

def test_loading_animation_captures_thread_exception(qtbot: QtBot) -> None:
    """Test that LoadingAnimation captures the thread exception when finished."""
    def failing_target() -> None:
        raise ValueError("test error")
    
    # Passing a nonexistent gif path is fine, QMovie will still instantiate and start
    anim = LoadingAnimation(gif_path="nonexistent.gif", target=failing_target)
    
    # Wait for the thread to finish executing
    qtbot.waitUntil(lambda: anim._thread.isFinished(), timeout=2000)
    
    # Call prepare_stop_animation manually to simulate movie frame loop check
    anim.prepare_stop_animation()
    
    assert isinstance(anim.exception, ValueError)
    assert str(anim.exception) == "test error"
    assert anim.animation_finished is True
    
    # Cleanup
    anim.deleteLater()
