from typing import Any

from loguru import logger

from app.models.settings import Settings


def apply_window_launch_state(
    window: Any, launch_state: str, custom_width: int, custom_height: int
) -> None:
    """
    Apply the window launch state to the given window.

    Args:
        window: The window instance to apply the launch state to.
        launch_state: The launch state string ("maximized", "normal", "custom").
        custom_width: The custom width to use if launch_state is "custom".
        custom_height: The custom height to use if launch_state is "custom".
    """
    if launch_state == "maximized":
        window.showMaximized()
    elif launch_state == "normal":
        window.showNormal()
    elif launch_state == "custom":
        # Validate custom size values
        custom_width, custom_height = Settings.validate_window_custom_size(
            custom_width, custom_height
        )
        window.resize(custom_width, custom_height)
        window.show()
    else:
        logger.warning(f"Unknown window launch state: {launch_state}")
