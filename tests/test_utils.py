import pytest
from mail2pr import Mail
from mail2pr.utils import slugify_subject
from pathlib import Path
import os


FIXTURE_DIR = Path(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")
)


def test_get_message_id():
    with open(FIXTURE_DIR / "1608054753.R10639372170588705026.wrt", 'rb') as fh:
        mail = Mail(fh)
        assert mail.message_id == "<20201215205639.31206-1-andreas@rammhold.de>"


def test_get_slug():
    with open(FIXTURE_DIR / "1608054753.R10639372170588705026.wrt", 'rb') as fh:
        mail = Mail(fh)
        assert mail.slug == "Add-a-new-file-to-the-repository"


@pytest.mark.parametrize('subject, slug', [
    ("abcdef01234ABCDEF", "abcdef01234ABCDEF"),
    ("abcdef01234 ABCDEF", "abcdef01234-ABCDEF"),
    (" whitespaces ", "whitespaces"),
    ("/*%-funny*/", "funny"),
    ("[PATCH] something: init at 1.3.3.7", "something-init-at-1.3.3.7"),
    ("[PATCH] add some amazing feature", "add-some-amazing-feature"),
    ("[PATCHv2] add some amazing feature", "add-some-amazing-feature"),
    ("Re: [PATCHv2] add some amazing feature", "add-some-amazing-feature"),
    ("Re: [PATCHv2] add some amazing feature 👾", "add-some-amazing-feature"),
])
def test_slugify_subject(subject, slug):
    assert slugify_subject(subject) == slug
