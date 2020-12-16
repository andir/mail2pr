from email.parser import BytesParser
from pathlib import Path
import subprocess
import shutil
import logging
import argparse
import os
import cmd
from tempfile import TemporaryDirectory, NamedTemporaryFile

from .utils import slugify_subject, create_cache_directory, sh, trim_subject


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
    def archive_url(self):
        """
        Return the archive url of the message
        """
        return self.email['Archived-At']

    @property
    def subject(self):
        """
        Return the subject without the [PATCH], Re:, … part
        """
        subject = self.email['subject']
        return trim_subject(subject)

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
    def __init__(self, repo_path: Path, base_branch: str, mail: Mail, github_user: str,
                 github_org: str, github_repo: str):
        self.mail = mail
        self.base_branch = base_branch
        self.github_user = github_user
        self.github_org = github_org
        self.github_repo = github_repo
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
        shutil.rmtree(str(self.path))
        sh(["git", "-C", self.repo_path, "worktree", "prune"])

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.cleanup()

    def log(self):
        """
        Get the commit log since the base branch ref
        """
        return sh(["git", "--no-pager", "log", f"refs/base-{self.branch_name}..{self.branch_name}"], stdout=subprocess.PIPE, text=True, cwd=self.worktree).stdout

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

    def pr(self):
        """
        Create a PR
        """

        log = self.log().strip()

        message = f'''{self.mail.subject}

I'm forwarding this patch that I received via email:

```
{log}
```
        '''
        if self.mail.archive_url:
            message += f'''
You can find the submission in the [archive]({self.mail.archive_url}).
            '''

        res = sh(["git", "push", "-f", f"ssh://git@github.com/{self.github_user}/{self.github_repo}.git", f"{self.branch_name}:{self.branch_name}"], check=False, cwd=self.worktree)

        if res.returncode != 0:
            print("Failed to push?!")
            return

        with NamedTemporaryFile() as fh:
            # hub pull-request --base OWNER:master --head MYUSER:my-branch
            fh.write(message.encode())
            fh.flush()
            res = sh(["hub", "pull-request", "--base", f"{self.github_org}:{self.base_branch}",
                "--head", f"{self.github_user}:{self.branch_name}",
                "-F", fh.name,
                "--edit",
               ], check=False, cwd=self.worktree)
            if res.returncode != 0:
                print("Failed to open PR")


class Shell(cmd.Cmd):
    intro = '''
        Run commands on the applied patches
    '''

    def __init__(self, worktree: Worktree, mail: Mail):
        super().__init__()
        self.mail = mail
        self.worktree = worktree

    def can_exit(self):
        return True

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

    def do_log(self, _arg):
        """
        Show the git log of the changes
        """
        print(self.worktree.log())

    def do_pr(self, _arg):
        """
        Create GitHub PR
        """
        self.worktree.pr()

    def do_quit(self, _arg):
        """
        Quit the shell
        """
        return True

    do_EOF = do_quit


def main():
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='Convert patches received via mail to pesky GitHub PRs')
    parser.add_argument('file', type=argparse.FileType('rb'))
    parser.add_argument('--base', type=str, default='master', help='The base branch this patch will be applied to')
    parser.add_argument('--repo', type=str, default=os.getcwd())
    parser.add_argument('--github-user', type=str, default='andir', help="Your username on GitHub")
    parser.add_argument('--github-org', type=str, default='andir', help="The GH org the target repo belongs to e.g. nixos for nixos/nixpkgs")
    parser.add_argument('--github-repo', type=str, default='mail2pr', help="The GH repo name within the org the target repo belongs to e.g. nixpkgs for nixos/nixpkgs")
    args = parser.parse_args()
    mail = Mail(args.file)
    with Worktree(args.repo, args.base, mail, args.github_user, args.github_org,
                  args.github_repo) as wt:
        try:
            wt.setup()
            Shell(wt, mail).cmdloop()
        except Exception as e:
            print(e)
    print("all done")


if __name__ == "__main__":
    main()
