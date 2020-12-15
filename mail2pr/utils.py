import re
import os
import subprocess
import logging
from typing import Union, List
from tempfile import TemporaryDirectory
from pathlib import Path

logger = logging.getLogger(__name__)


def sh(command: List[str], cwd=None, input=None, check=True):
    logging.info("$ " + ' '.join(command))
    return subprocess.run(command, check=check, cwd=cwd, input=input)


def slugify_subject(subject: str) -> str:
    """
    Returns a string that is safe for usage as git branch name.
    """
    subject = subject.strip()
    subject = subject.lstrip('Re:').lstrip()
    subject = subject.lstrip('re:').lstrip()
    subject = subject.lstrip(':').lstrip()

    if subject.startswith('['):
        # strip [PATCH] and other prefixes in brackets
        m = re.match(r"^\[[^\]]+\](?P<subject>.+)$", subject)
        if m:
            subject = m.group('subject').strip()

    # finally replace everything that isn't 0-9a-bA-B. with -
    subject = re.sub(r"[^0-9a-zA-Z\.]", "-", subject)
    # remove double/triple/… dashes
    subject = re.sub(r"--+", "-", subject)
    # remoe dashes at the start and the end
    subject = re.sub(r"^-", "", subject)
    subject = re.sub(r"-$", "", subject)

    return subject


def create_cache_directory(name: str) -> Union[Path, "TemporaryDirectory[str]"]:
    """
    Gets the "best" directory for a temporary directory according to
    XDG_CACHE_HOME or as fallback ~/.cache

    Mostly copied for Jörgs nixpkgs-review
    https://github.com/mic92/nixpkgs-review
    License: MIT
    """
    xdg_cache_raw = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_raw is not None:
        xdg_cache = Path(xdg_cache_raw)
    else:
        home = os.environ.get("HOME", None)
        if home is None:
            # we are in a temporary directory
            return TemporaryDirectory(prefix=name)
        else:
            xdg_cache = Path(home).joinpath(".cache")

    counter = 0
    while True:
        try:
            final_name = name if counter == 0 else f"{name}-{counter}"
            cache_home = xdg_cache.joinpath("mail2pr", final_name)
            cache_home.mkdir(parents=True)
            return cache_home
        except FileExistsError:
            counter += 1

