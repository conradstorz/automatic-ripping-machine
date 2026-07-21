"""Shared inactivity watchdog for external processes.

Generalizes the makemkvcon watchdog: run an external command and kill it if it
shows no sign of life for `inactivity` seconds, where "sign of life" is the
freshest of {a new stdout line, an update to a progress file}. A healthy long
job (transcode/rip) keeps emitting progress, so it is never killed; a wedged one
goes silent and is reaped instead of hanging the ripper forever.

This module is dependency-light (stdlib + psutil) so it can be imported by
makemkv.py, handbrake.py, ffmpeg.py and utils.py without import cycles.
"""
import logging
import os
import queue
import subprocess
import threading
import time

import psutil

_STDOUT_SENTINEL = object()
WATCHDOG_POLL_SECS = 5


class ProcessInactivityError(Exception):
    """Raised when a watched process is killed for showing no sign of life."""


def kill_process_tree(pid):
    """
    Best-effort SIGTERM then SIGKILL of a process and all its descendants.
    Safe to call for a pid that has already exited.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        procs = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        procs = []
    procs.append(parent)
    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=5)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass


def heartbeat_idle(last_output, progress_file, now):
    """
    Seconds since the most recent sign of life: a stdout line OR an update to
    `progress_file` (a log/output file the tool writes while it works). Whichever
    is fresher wins, so a job that writes progress to a file (silent stdout) is
    not falsely judged idle.
    """
    idle = now - last_output
    if progress_file:
        try:
            idle = min(idle, now - os.path.getmtime(progress_file))
        except OSError:
            pass
    return idle


def _drain_stdout(stream, line_queue):
    """Reader-thread body: push each line onto the queue, then a sentinel."""
    try:
        for line in stream:
            line_queue.put(line)
    finally:
        line_queue.put(_STDOUT_SENTINEL)


def run_watched(cmd, inactivity, progress_file=None, shell=False, on_line=None):
    """
    Run `cmd`, streaming its merged stdout/stderr, and kill it if it shows no
    sign of life for `inactivity` seconds.

    Parameters:
        cmd: argv list (or a string when shell=True).
        inactivity (int|None): seconds of no-sign-of-life before the process is
            killed. <=0 or None disables the watchdog (blocks like a plain run).
        progress_file (str|None): a file the tool updates while working; a fresh
            mtime counts as a heartbeat (for tools whose progress is not on stdout).
        shell (bool): passed to Popen.
        on_line (callable|None): called with each stdout line (without newline),
            e.g. to parse progress.
    Returns:
        str: the captured stdout/stderr.
    Raises:
        ProcessInactivityError: the process was killed for going silent.
        subprocess.CalledProcessError: the process exited non-zero.
    """
    if inactivity is not None and inactivity <= 0:
        inactivity = None  # disabled
    buffer = []
    # stdin=DEVNULL so a prompting child can never block waiting on input.
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, text=True, shell=shell) as proc:
        line_queue = queue.Queue()
        reader = threading.Thread(target=_drain_stdout, args=(proc.stdout, line_queue),
                                  daemon=True)
        reader.start()
        last_output = time.time()
        try:
            while True:
                poll = min(inactivity, WATCHDOG_POLL_SECS) if inactivity else None
                try:
                    item = line_queue.get(timeout=poll)
                except queue.Empty:
                    item = None
                if item is _STDOUT_SENTINEL:
                    break
                if item is not None:
                    last_output = time.time()
                    line = item.rstrip("\n")
                    buffer.append(line)
                    if on_line is not None:
                        on_line(line)
                if inactivity and heartbeat_idle(last_output, progress_file, time.time()) >= inactivity:
                    logging.error(f"Process (PID {proc.pid}) showed no activity for "
                                  f"{inactivity}s; assuming it is hung. Killing it. cmd={cmd}")
                    kill_process_tree(proc.pid)
                    raise ProcessInactivityError(
                        f"process hung: no activity for {inactivity}s: {cmd}")
        finally:
            # Never let Popen.__exit__'s wait() block on a live child; reap on any
            # exit (including an early raise) so nothing is orphaned.
            if proc.poll() is None:
                kill_process_tree(proc.pid)
    output = "\n".join(buffer)
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=output)
    return output
