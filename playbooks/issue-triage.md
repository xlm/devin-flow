# Issue triage

Triage a newly opened GitHub issue in the repository it was filed against.
The triggering issue payload is appended to this prompt. Finish by
reporting structured output with an `outcome` of `duplicate`,
`not_a_bug`, `not_reproducible` or `fixed`, plus `duplicate_of` for
duplicates and `pr_url` for fixes. Always include `issue_url`,
`issue_number` and `issue_title` of the triggering issue in the
structured output.

## Procedure

1. Read the issue title, body and labels. Identify the repository from the
   payload and clone it if it is not already present.
2. Check for duplicates. Search open and recently closed issues in the same
   repository for the same symptom, error message or stack trace. If you
   find an existing issue describing the same problem, comment on the new
   issue linking the existing one, add the `duplicate` label, close the new
   issue as a duplicate, and stop with outcome `duplicate` and
   `duplicate_of` set to the existing issue URL.
3. Classify the issue. If it is not a bug report (feature request,
   question, discussion), add the `enhancement` label for a feature request
   or `question` otherwise, comment briefly explaining that this triage only
   handles bug reports and that a maintainer will follow up, leave the issue
   open, and stop with outcome `not_a_bug`.
4. Reproduce the bug. Follow the steps in the issue against the default
   branch. Write a failing test or a minimal script that demonstrates the
   problem. Time-box this to a reasonable effort.
5. If you cannot reproduce it, comment on the issue with exactly what you
   tried (commands, versions, branch, observed behaviour), ask the reporter
   to reopen or file a new issue with reproducible steps, add the
   `needs-repro` label, and close the issue. Stop with outcome
   `not_reproducible`.
6. If you can reproduce it, add the `bug` label, fix the root cause, keep
   the reproduction as a regression test, run the repository's lint and
   test commands, and open a pull request whose description contains
   `Fixes #<issue number>`. Comment on the issue linking the pull request
   and leave it open so the merge closes it. Finish with outcome `fixed`
   and `pr_url` set.

## Rules

- Close an issue only when it is a duplicate or not reproducible. Never
  close a feature request, question, or a bug you fixed.
- Apply exactly one label per issue: `duplicate`, `enhancement` or
  `question`, `needs-repro`, or `bug`. Use `gh issue edit --add-label`.
  The labels exist in the repository, do not create new ones.
- Keep comments factual and short; include the evidence, not the process.
- Do not open a pull request without a reproduction.
