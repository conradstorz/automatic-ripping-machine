"""
Function definition
  Wrapper for the python subprocess module
"""

import logging
import subprocess
from typing import Optional, List, Union

import arm.config.config as cfg


def _timeout_secs(timeout):
    """Resolve the wall-clock timeout: explicit arg, else SUBPROCESS_TIMEOUT_SECS
    (default 60); 0/None-in-config disables (returns None = no timeout)."""
    if timeout is not None:
        return timeout if timeout > 0 else None
    try:
        val = int(cfg.arm_config.get('SUBPROCESS_TIMEOUT_SECS', 60))
    except (TypeError, ValueError):
        val = 60
    return val if val > 0 else None


def arm_subprocess(cmd: Union[str, List[str]], shell=False, check=False, timeout=None) -> Optional[str]:
    """
    Spawn blocking subprocess

    :param cmd: Command to run
    :param shell: Run ``cmd`` in a shell
    :param check: Raise ``CalledProcessError``/``TimeoutExpired`` if ``cmd`` fails or hangs
    :param timeout: Wall-clock seconds before the command is killed; defaults to the
        SUBPROCESS_TIMEOUT_SECS config value. These are short helper commands, so a hang
        (bad media, unreachable device) is aborted instead of blocking the job forever.

    :return: Output (both stdout and stderr) of ``cmd``, or ``None`` if it failed/timed out

    :raise CalledProcessError:
    :raise TimeoutExpired:
    """
    arm_process = None
    logging.debug(f"Running command: {cmd}")
    try:
        arm_process = subprocess.check_output(
            cmd,
            shell=shell,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            timeout=_timeout_secs(timeout),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        decoded_output: Optional[str] = None
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            decoded_output = error.output.strip()
        logging.error(
            f"Error while running command: {cmd}\n"
            + (
                f"Output was: {decoded_output}"
                if decoded_output
                else "The command produced no output."
            ),
            exc_info=error,
        )
        if check:
            raise error

    return arm_process
