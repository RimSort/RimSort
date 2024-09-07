import os
import shutil
import sys
from pathlib import Path

from loguru import logger


class SymlinkCreationError(Exception):
    """Exception related to creating a symlink/junction."""

    def __init__(
        self, message: str, src_path: str | Path, dst_path: str | Path
    ) -> None:
        super().__init__(message)
        self.src_path = Path(src_path)
        self.dst_path = Path(dst_path)


class SymlinkDstNotEmptyError(SymlinkCreationError):
    """Exception raised when the destination path for a symlink/junction is an existing non-empty directory."""


class SymlinkDstIsFileError(SymlinkCreationError):
    """Exception raised when the destination path for a symlink/junction is an existing file."""


class SymlinkSrcNotExistError(SymlinkCreationError):
    """Exception raised when the source path for a symlink/junction."""


class SymlinkSrcNotDirError(SymlinkCreationError):
    """Exception raised when the source path for a symlink/junction is not a directory. This is to ensure compatibility with Windows junctions."""


class SymlinkDstParentNotExistError(SymlinkCreationError):
    """Exception raised when the parent directory of the destination path for a symlink/junction does not exist."""


def is_junction_or_link(path: str | Path) -> bool:
    """
    This checks if a path is a symlink.
    Additionally on Windows it checks if the path is a junction.
    If the path does not exist or is not a symlink/junction,
    it will catch an OSError, and return false.
    :param path: The path to check
    """
    try:
        return bool(os.readlink(path))
    except OSError:
        return False


def create_symlink(
    src_path: str,
    dst_path: str,
    force: bool = False,
) -> None:
    """
    Creates a symlink/junction from src_path to dst_path. The src_path must exist and be a directory (for compatibility with Windows junctions).

    Symlinks are made on Unix systems using os.symlink, and junctions on Windows using the CreateJunction function from _winapi.

    Note that this method will not convert relative paths to absolute paths before system calls.
    If symlink creation on Windows fails, force is true, and src_path is a directory, it will attempt to create a junction instead. Otherwise, SymlinkCreationError will be raised.

    This method logs errors, warnings, and debug messages using loguru.

    If the dst_path exists and force is False:
        - If dst_path is a symlink/junction, it will be unlinked re-created based on method args.
        - If dst_path is a directory and empty, it will be deleted.
        - If dst_path is a directory and not empty, SymlinkCreationError will be raised.
        - If dst_path is a file, SymlinkCreationError will be raised.
    If the dst_path exists and force is True:
        - dst_path will be removed (even if it is a non-empty directory) and re-created based on method args, even if it already exists.

    :param src_path: The source path/target to create the symlink from. Must be a directory
    :type src_path: str
    :param dst_path: The destination path to create the symlink to.
    :type dst_path: str
    :param force: Force the creation of the symlink/junction, even if the dst_path exists. Default is False.
    """
    if not os.path.exists(src_path):
        logger.warning(
            f"Provided source path {src_path} either does not exist, abandoning symlink creation."
        )
        raise SymlinkSrcNotExistError(
            f"Provided source path {src_path} either does not exist, abandoning symlink creation.",
            src_path,
            dst_path,
        )

    if not os.path.isdir(src_path):
        logger.warning(
            f"Provided source path {src_path} is not a directory, abandoning symlink creation."
        )
        raise SymlinkSrcNotDirError(
            f"Provided source path {src_path} is not a directory, abandoning symlink creation.",
            src_path,
            dst_path,
        )

    if os.path.exists(dst_path):
        logger.debug(
            f"Potential existing link at {dst_path}. Will attempt to recreate to source: {src_path}"
        )
        # Remove by type
        if is_junction_or_link(dst_path) or os.path.ismount(dst_path):
            os.unlink(dst_path)
        elif os.path.isdir(dst_path) and not os.listdir(dst_path):
            os.rmdir(dst_path)
        elif os.path.isdir(dst_path):
            msg = f"Symlink destination path {dst_path} is a non-empty directory."

            if force:
                logger.debug(msg + " Forcing deletion of non-empty directory.")
                shutil.rmtree(dst_path)
            else:
                logger.warning(msg)
                raise SymlinkDstNotEmptyError(
                    msg,
                    src_path,
                    dst_path,
                )
        else:
            # Dst path is a file
            msg = f"Symlink destination path {dst_path} exists and seems to be a file."

            if force:
                logger.debug(msg + " Forcing deletion of file.")
                os.remove(dst_path)
            else:
                logger.warning(msg)
                raise SymlinkDstIsFileError(
                    msg,
                    src_path,
                    dst_path,
                )

    elif not os.path.exists(os.path.dirname(dst_path)):
        msg = f"Symlink destination parent directory {os.path.dirname(dst_path)} does not exist."
        if force:
            logger.debug(msg + " Forcing creation of parent directory.")
            os.makedirs(os.path.dirname(dst_path))
        else:
            logger.warning(msg)

            raise SymlinkDstParentNotExistError(
                msg,
                src_path,
                dst_path,
            )

    if sys.platform != "win32":
        os.symlink(
            src_path,
            dst_path,
            target_is_directory=os.path.isdir(src_path),
        )
        return
    elif sys.platform == "win32":
        from _winapi import CreateJunction

        CreateJunction(src_path, dst_path)

    else:
        raise NotImplementedError(
            f"Platform {sys.platform} is not supported for symlink/junction creation"
        )
