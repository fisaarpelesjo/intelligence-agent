# GitHub Ruleset Proposal

`.github/rulesets/main.yml` documents the intended `main` protection policy. It is not applied automatically.

Required policy:

- prohibit direct push to `main`;
- require pull request;
- require mandatory checks;
- prohibit force push;
- prohibit deletion of `main`;
- require conversation resolution;
- allow only squash merge;
- allow auto-merge after gates;
- remove branch after merge.

Review the repository-specific status check names before applying the ruleset remotely.

