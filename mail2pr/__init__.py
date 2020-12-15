from email.parser import BytesParser
from pathlib import Path
import shutil
import logging
import argparse
import os
import cmd
from tempfile import TemporaryDirectory

from .utils import slugify_subject, create_cache_directory, sh


class Mail:
    def __init__(self, file):
        self.email = BytesParser().parse(file)

    @property
    def message_id(self):
        """
        Return the message id as written in the mail header.
        """
        return self.email['message-id']

    @property
    def slug(self):
        """
        Return a slugified version of the mail's subject to be used as Git
        branch name.
        """
        subject = self.email['subject']
        return slugify_subject(subject)

    def as_bytes(self):
        return self.email.as_bytes()


class GitAMFailed(Exception):
    pass


class GitFetchFailed(Exception):
    pass


class GitWorktreeAddFailed(Exception):
    pass


class Worktree:
    def __init__(self, repo_path: Path, base_branch: str, mail: Mail):
        self.mail = mail
        self.base_branch = base_branch
        self._tempdir = create_cache_directory(name=mail.slug)
        if isinstance(self._tempdir, TemporaryDirectory):
            self.path = Path(self._tempdir.name)
        else:
            self.path = self._tempdir

        self.branch_name = f"ml2pr/{self.mail.slug}"

        self.repo_path = repo_path
        self.worktree = self.path / "repo"
        self.worktree.mkdir()

    def setup(self):
        try:
            sh(["git", "-C", self.repo_path, "fetch", "origin", f"{self.base_branch}:refs/base-{self.branch_name}"])
        except Exception as e:
            raise GitFetchFailed(e)

        sh(["git", "-C", self.repo_path, "branch", "-f", self.branch_name,
            f"refs/base-{self.branch_name}"])

        try:
            sh(["git", "-C", self.repo_path, "worktree", "add", str(self.worktree),
                self.branch_name])
        except Exception as e:
            raise GitFetchFailed(e)

        try:
            b = self.mail.as_bytes()
            sh(["git", "am", "--message-id", "-"],
               cwd=self.worktree,
               input=b)
        except Exception as e:
            raise GitAMFailed(e)

    def cleanup(self):
        shutil.rmtree(self.path)
        sh(["git", "-C", self.repo_path, "worktree", "prune"])

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, type, value, traceback):
        self.cleanup()

    def eval(self, expression='nixos/release-combined.nix'):
        """
        Eval the repo after applying this patch.
        """
        sh(["nix-instantiate", "--eval", expression], cwd=self.worktree)

    def build(self, expression):
        """
        Eval the repo after applying this patch.
        """
        sh(["nix-build", expression], cwd=self.worktree)

    def shell(self):
        """
        Launch a shell in the checkout
        """
        return sh(["bash"], cwd=self.worktree, check=False)

    def review(self):
        """
        Run nixpkgs-review
        """
        sh(["nixpkgs-review", "rev", "--no-shell", "-b",
            self.base_branch, self.branch_name]
                , cwd=self.repo_path)


class Shell(cmd.Cmd):
    
    intro = '''
        Run commands on the applied patches
    '''

    def __init__(self, worktree: Worktree, mail: Mail):
        super().__init__()
        self.mail = mail
        self.worktree = worktree

    def do_eval(self, arg):
        """
        Eval the given expression
        """
        self.worktree.eval(arg)

    def do_build(self, arg):
        """
        Eval the given expression
        """
        self.worktree.build(arg)

    def do_shell(self, _arg):
        """
        Launch interactive shell within the worktree
        """
        self.worktree.shell()

    def do_review(self, _arg):
        """
        Run nixpkgs-review on the changes
        """
        self.worktree.review()


def main():
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='Convert patches received via mail to pesky GitHub PRs')
    parser.add_argument('file', type=argparse.FileType('rb'))
    args = parser.parse_args()
    base_branch = "master"
    mail = Mail(args.file)
    with Worktree(os.getcwd(), base_branch, mail) as wt:
        Shell(wt, mail).cmdloop()
    print("all done")


if __name__ == "__main__":
    main()
