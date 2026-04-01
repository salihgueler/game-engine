"""Container-based sandbox runner using Finch for secure code execution.

Security:
- No network access (--network none)
- Non-root user inside container
- Read-only root filesystem (--read-only)
- No privilege escalation (--security-opt=no-new-privileges)
- Memory and CPU limits
- Execution timeout

Performance:
- Pre-built language-specific images (alpine-based, minimal layers)
- Containers are ephemeral (--rm) — no cleanup needed
- Code passed via stdin to avoid volume mounts
"""
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)

# Image names for each supported language
SANDBOX_IMAGES = {
    "python": os.environ.get("SANDBOX_IMAGE_PYTHON", "quest-sandbox-python:latest"),
    "java": os.environ.get("SANDBOX_IMAGE_JAVA", "quest-sandbox-java:latest"),
    "typescript": os.environ.get("SANDBOX_IMAGE_TYPESCRIPT", "quest-sandbox-typescript:latest"),
}

# Execution timeout in seconds
SANDBOX_TIMEOUT = int(os.environ.get("SANDBOX_TIMEOUT", "30"))

# Resource limits
SANDBOX_MEMORY = os.environ.get("SANDBOX_MEMORY", "128m")
SANDBOX_CPUS = os.environ.get("SANDBOX_CPUS", "0.5")


def _get_finch_cmd():
    """Get the finch binary path."""
    return os.environ.get("FINCH_PATH", "finch")


def run_code(language: str, code: str, stdin_data: str = "") -> dict:
    """Run code in a sandboxed container.

    Args:
        language: One of 'python', 'java', 'typescript'
        code: The source code to execute
        stdin_data: Optional stdin input for the program

    Returns:
        dict with keys: success, stdout, stderr, timed_out
    """
    lang_key = language.lower().strip()
    image = SANDBOX_IMAGES.get(lang_key)
    if not image:
        logger.warning("Unsupported language requested: %s", language)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unsupported language: {language}. Supported: {list(SANDBOX_IMAGES.keys())}",
            "timed_out": False,
        }

    logger.info("Sandbox run starting: language=%s, image=%s, code_length=%d", lang_key, image, len(code))
    start_time = time.monotonic()

    try:
        if lang_key == "python":
            result = _run_python(image, code, stdin_data)
        elif lang_key == "java":
            result = _run_java(image, code, stdin_data)
        elif lang_key == "typescript":
            result = _run_typescript(image, code, stdin_data)
        else:
            result = None

        elapsed = time.monotonic() - start_time

        if result is None:
            logger.error("Sandbox run failed: language=%s matched image but no runner", lang_key)
            return {"success": False, "stdout": "", "stderr": f"No runner for {language}", "timed_out": False}

        logger.info(
            "Sandbox run complete: language=%s, success=%s, timed_out=%s, duration=%.2fs, stdout_length=%d, stderr_length=%d",
            lang_key, result["success"], result["timed_out"], elapsed, len(result["stdout"]), len(result["stderr"]),
        )
        if not result["success"]:
            logger.info("Sandbox run stderr: language=%s, stderr=%.500s", lang_key, result["stderr"])

        return result

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error("Sandbox execution error: language=%s, duration=%.2fs, error=%s", language, elapsed, e)
        return {"success": False, "stdout": "", "stderr": str(e), "timed_out": False}


def _finch_run(image: str, cmd_args: list, stdin_data: str = "", extra_volumes: list = None) -> dict:
    """Execute a finch run command with sandbox security constraints."""
    finch = _get_finch_cmd()

    run_cmd = [
        finch, "run", "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--security-opt", "no-new-privileges",
        "--memory", SANDBOX_MEMORY,
        "--cpus", SANDBOX_CPUS,
        "--pids-limit", "64",
    ]

    if extra_volumes:
        for v in extra_volumes:
            run_cmd.extend(["-v", v])

    run_cmd.append(image)
    run_cmd.extend(cmd_args)

    try:
        result = subprocess.run(
            run_cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Execution timed out", "timed_out": True}


def _run_python(image: str, code: str, stdin_data: str) -> dict:
    """Run Python code. Passed directly via entrypoint arg."""
    return _finch_run(image, [code], stdin_data)


def _run_java(image: str, code: str, stdin_data: str) -> dict:
    """Run Java code. Write to a temp file, mount read-only, compile and run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Resolve symlinks for Finch VM volume mounts (macOS /var -> /private/var)
        real_tmpdir = os.path.realpath(tmpdir)
        os.chmod(real_tmpdir, 0o755)
        src_path = os.path.join(real_tmpdir, "Solution.java")
        with open(src_path, "w") as f:
            f.write(code)
        os.chmod(src_path, 0o644)

        # Mount source dir read-only, use /tmp inside container for class files
        shell_cmd = (
            "cp /src/Solution.java /tmp/Solution.java && "
            "cd /tmp && "
            "java Solution.java"
        )
        return _finch_run(
            image,
            [shell_cmd],
            stdin_data,
            extra_volumes=[f"{real_tmpdir}:/src:ro"],
        )


def _run_typescript(image: str, code: str, stdin_data: str) -> dict:
    """Run TypeScript code. Write to temp file, mount read-only, execute with tsx."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Resolve symlinks for Finch VM volume mounts (macOS /var -> /private/var)
        real_tmpdir = os.path.realpath(tmpdir)
        os.chmod(real_tmpdir, 0o755)
        src_path = os.path.join(real_tmpdir, "solution.ts")
        with open(src_path, "w") as f:
            f.write(code)
        os.chmod(src_path, 0o644)

        shell_cmd = "tsx /src/solution.ts"
        return _finch_run(
            image,
            [shell_cmd],
            stdin_data,
            extra_volumes=[f"{real_tmpdir}:/src:ro"],
        )
