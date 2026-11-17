# Claude Worktree Check

Find Claude Code project hooks that are missing or different in a Git worktree. Run this from the checkout whose configuration you expect your other worktrees to match. Requires Python 3.10+ and Git.

```sh
python path/to/check.py --base path/to/my-project
```

Example output:

```text
my-project/.claude/worktrees/review
  .claude/settings.local.json | 'PreToolUse': 1 missing, 0 different or additional
```

The check compares hook entries and the `disableAllHooks` value in `.claude/settings.json` and `.claude/settings.local.json` independently across registered worktrees. It reports counts by event without printing commands or their arguments. It reads files and Git metadata only. Exit codes are `0` for a match, `1` for differences, and `2` when the comparison cannot complete.

If the settings file is tracked, review the worktree branch and merge the intended configuration. For deliberately ignored files, review [Claude Code’s worktree documentation](https://code.claude.com/docs/en/worktrees) for `.worktreeinclude` and check the worktree after creation. Only include the exact files you intend to copy.

This compares the declared project settings. Actual execution also depends on hook order, user and plugin configuration, and whether the referenced scripts exist and run. See [the upstream issue](https://github.com/anthropics/claude-code/issues/83953) for the reported failure.

MIT licensed. An independent project for Claude Code users.
