import platform
from enum import Enum, auto, unique


class SystemInfo:
    """
    A singleton class that provides information about the system's operating system and architecture.

    Attributes:
        _instance: The singleton instance of the `SystemInfo` class.
        _operating_system: The detected operating system.
        _architecture: The detected system architecture.

    Examples:
        >>> info = SystemInfo()
        >>> print(info.operating_system)
        >>> print(info.architecture)
    """

    _instance = None  # type: SystemInfo | None
    _operating_system = None  # type: SystemInfo.OperatingSystem | None
    _architecture = None  # type: SystemInfo.Architecture | None

    @unique
    class OperatingSystem(Enum):
        """
        An enumeration representing the possible operating systems.

        Attributes:
            WINDOWS: Represents the Windows OS.
            LINUX: Represents the Linux OS.
            MACOS: Represents the macOS.
        """

        WINDOWS = auto()
        LINUX = auto()
        MACOS = auto()

    @unique
    class Architecture(Enum):
        """
        An enumeration representing the possible system architectures.

        Attributes:
            X86: Represents the x86 architecture (32-bit).
            X64: Represents the x64 architecture (64-bit).
            ARM64: Represents the ARM64 architecture.
        """

        X86 = auto()
        X64 = auto()
        ARM64 = auto()

    def __new__(cls) -> "SystemInfo":
        """
        Create a new instance or return the existing singleton instance of the `SystemInfo` class.
        """
        if not cls._instance:
            cls._instance = super(SystemInfo, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize the `SystemInfo` instance by detecting the operating system and architecture.
        """
        if hasattr(self, "_is_initialized") and self._is_initialized:
            return

        if platform.system() in ["Windows"]:
            self._operating_system = SystemInfo.OperatingSystem.WINDOWS
        elif platform.system() in ["Linux"]:
            self._operating_system = SystemInfo.OperatingSystem.LINUX
        elif platform.system() in ["Darwin"]:
            self._operating_system = SystemInfo.OperatingSystem.MACOS
        else:
            raise UnsupportedOperatingSystemError(
                f"Unsupported operating system detected: {platform.system()}."
            )

        if platform.machine() in ["x86_64", "AMD64"]:
            self._architecture = SystemInfo.Architecture.X64
        elif platform.machine() in ["arm64", "aarch64"]:
            self._architecture = SystemInfo.Architecture.ARM64
        else:
            raise UnsupportedArchitectureError(
                f"Unsupported architecture detected: {platform.machine()}."
            )

        self._is_initialized: bool = True

    @property
    def operating_system(self) -> OperatingSystem | None:
        """
        Get the detected operating system.

        Returns:
            The detected operating system as an instance of `SystemInfo.OperatingSystem`.
        """
        return self._operating_system

    @property
    def architecture(self) -> Architecture | None:
        """
        Get the detected system architecture.

        Returns:
            The detected architecture as an instance of `SystemInfo.Architecture`.
        """
        return self._architecture


class UnsupportedOperatingSystemError(Exception):
    """
    Exception raised when an unsupported operating system is detected.
    """

    pass


class UnsupportedArchitectureError(Exception):
    """
    Exception raised when an unsupported system architecture is detected.
    """

    pass
