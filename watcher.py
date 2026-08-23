import psutil


def check_process_alive(task):
    """Returns True/False for pid- or process_name-watched tasks, None if task isn't process-watched.

    Note: this can only detect that a watched process is still running vs. has exited -
    it cannot know whether the process ultimately succeeded or failed, so process-watched
    tasks are always marked 'done' (never 'failed') when they exit. Use the status-file
    mechanism instead if you need a real success/failure distinction.
    """
    pid = task.get("pid")
    name = task.get("process_name")
    if pid:
        return psutil.pid_exists(pid)
    if name:
        for p in psutil.process_iter(["name"]):
            try:
                if p.info["name"] and p.info["name"].lower() == name.lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    return None
