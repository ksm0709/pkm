# CHANGELOG

<!-- version list -->

## v2.10.0 (2026-04-06)

### Chores

- Remove unintended files created during translation
  ([`fa546f1`](https://github.com/ksm0709/pkm/commit/fa546f1d2e90903eedd3c4242d43df34a113780e))

### Features

- **workflows**: Introduce zettel-loop and refine-loop as canonical top-level orchestrators
  ([`b365815`](https://github.com/ksm0709/pkm/commit/b365815be23c3c839cbb2903658ceeecc8c3a843))


## v2.9.0 (2026-04-06)

### Bug Fixes

- Sync commands/skills on setup and update, removing stale files
  ([`ace07d3`](https://github.com/ksm0709/pkm/commit/ace07d370a90422dcbb9611641614724b7de695e))

- Use git pull --ff-only to avoid divergent branch prompt
  ([`9450ef3`](https://github.com/ksm0709/pkm/commit/9450ef3c41075635f295237fd624fe0f95006c2a))

### Features

- Restore dream as meta-workflow, add distill-daily and prune-merge-split
  ([`f94cb5d`](https://github.com/ksm0709/pkm/commit/f94cb5dc9188c8c800a044c0122616936086a5c1))

- Setup remembers previous choices, skips prompts on reuse
  ([`3e8028d`](https://github.com/ksm0709/pkm/commit/3e8028dc1455ea800f76ec1ff936a3938f49fcd0))


## v2.8.0 (2026-04-06)

### Features

- Install commands to ~/.agents/commands/pkm/ as well
  ([`d59ed81`](https://github.com/ksm0709/pkm/commit/d59ed8116638af07fbe0b98fd6a3e3677981a11e))

### Refactoring

- Add-workflow now uses Socratic interview with ambiguity scoring
  ([`6ae792a`](https://github.com/ksm0709/pkm/commit/6ae792a782a33dff3da24c84d7dd46dff2bd65b6))


## v2.7.0 (2026-04-06)

### Features

- Add /pkm:add-workflow wizard command
  ([`2fcbf7b`](https://github.com/ksm0709/pkm/commit/2fcbf7be77b43db58026b95f472abc857ca54fb3))


## v2.6.1 (2026-04-06)

### Bug Fixes

- Update setup.py help text to reflect renamed commands
  ([`74b8baf`](https://github.com/ksm0709/pkm/commit/74b8baf8b1ffde8723f4cfa6cd5778bcf8a9c3e5))

### Refactoring

- Rename ambiguous workflow names for clarity
  ([`2f96061`](https://github.com/ksm0709/pkm/commit/2f9606113a899aaea2d42e2cf1fc4c4a837eb4c0))

- Rename link-notes → auto-linking
  ([`92d8de1`](https://github.com/ksm0709/pkm/commit/92d8de1cc6ae16f7b56ea2b8f18b1b08dbc927f4))


## v2.6.0 (2026-04-06)

### Features

- Add /pkm:<workflow> Claude Code slash commands
  ([`4be0f73`](https://github.com/ksm0709/pkm/commit/4be0f73ce014baa08692aa763db92251a1c6f599))


## v2.5.3 (2026-04-06)

### Bug Fixes

- Setup and update work without a local source dir (curl|bash installs)
  ([`915a785`](https://github.com/ksm0709/pkm/commit/915a7855545d7f71a18d88323976519ff82f6c10))


## v2.5.2 (2026-04-06)

### Bug Fixes

- Pkm update re-downloads from GitHub when no local git repo
  ([`a0d0720`](https://github.com/ksm0709/pkm/commit/a0d0720dac6e126e0adecbd82818f484a069986b))


## v2.5.1 (2026-04-06)

### Bug Fixes

- Make install.sh work when piped via curl | bash
  ([`e97b060`](https://github.com/ksm0709/pkm/commit/e97b0603a45dfd93a005758be4ab59110bb0099e))


## v2.5.0 (2026-04-06)

### Features

- Add backlinks, tag index notes, and git vault naming
  ([`28bbee6`](https://github.com/ksm0709/pkm/commit/28bbee66f47ec0c298f8e3a3d6d529d001f3003f))


## v2.4.0 (2026-04-05)

### Features

- **agent**: Inject PKM role directive in turn-start hook
  ([`2d4bfa6`](https://github.com/ksm0709/pkm/commit/2d4bfa67fa8b812a97218307bf5f1365a611df70))


## v2.3.1 (2026-04-05)

### Bug Fixes

- **agent**: Update hook hints to use pkm note/daily commands
  ([`4bd7315`](https://github.com/ksm0709/pkm/commit/4bd7315d307a2a412f325643e60ac926520f9559))


## v2.3.0 (2026-04-05)

### Bug Fixes

- **config**: Include missing get_vault_context implementation
  ([`99af0f2`](https://github.com/ksm0709/pkm/commit/99af0f2f34aad08fbbdf9bfdf99a8fdff509b79f))

### Features

- **cli**: Display active vault and its resolution source on main command and vault list
  ([`9017a6c`](https://github.com/ksm0709/pkm/commit/9017a6c7acb6f0b12a13b5313be185438d90fccb))


## v2.2.0 (2026-04-05)

### Features

- **config**: Add auto git project vault mapping and local config support
  ([`27d5fbc`](https://github.com/ksm0709/pkm/commit/27d5fbcd819ef870aea800c18bc1be95107527e1))


## v2.1.0 (2026-04-05)

### Bug Fixes

- Update pkm new → pkm note add after v2.0.0 rename
  ([`2885425`](https://github.com/ksm0709/pkm/commit/28854253beedb437f2a61517c0f60b01d86b00b8))

### Chores

- Remove accidentally committed OMC state file
  ([`d26b811`](https://github.com/ksm0709/pkm/commit/d26b8112dbff970d9a1e87d95350b2a267e301a4))

### Continuous Integration

- Remove unused latest moving tag step
  ([`a13e88a`](https://github.com/ksm0709/pkm/commit/a13e88af8fa2008530958a51e49b056b888b4bdc))

### Documentation

- Update README to v2.0.0 with new command structure
  ([`b4b3b1e`](https://github.com/ksm0709/pkm/commit/b4b3b1ee3e691524bef3b8cce1385a6799e5f90e))

### Features

- **memory**: PKM as LLM agent memory layer
  ([`171e935`](https://github.com/ksm0709/pkm/commit/171e935cc2cbf08231ec0361a927deebf5bf22b1))

### Refactoring

- **memory**: Migrate pkm memory → pkm note add + pkm search
  ([`3daa763`](https://github.com/ksm0709/pkm/commit/3daa763727973298ddb3029989c0deba6586297f))


## v2.0.1 (2026-04-05)

### Bug Fixes

- **setup**: Install skill to ~/.agents/skills/pkm/ in addition to ~/.claude
  ([`7f23ec2`](https://github.com/ksm0709/pkm/commit/7f23ec2ab61e80116f2b5b665302db148d2cb597))


## v2.0.0 (2026-04-05)

### Features

- **note**: Add pkm note command group (add/edit/show/stale/orphans)
  ([`c3cd8a4`](https://github.com/ksm0709/pkm/commit/c3cd8a462e56da94f050cc01f05709d4b38295a9))

### Breaking Changes

- **note**: Pkm new, pkm stale, pkm orphans removed from top-level


## v1.1.2 (2026-04-05)

### Performance Improvements

- Lazy-import sentence-transformers to eliminate startup delay
  ([`4984b34`](https://github.com/ksm0709/pkm/commit/4984b34636863538fa7bb0ab6942a6b3f80bdbdd))


## v1.1.1 (2026-04-05)

### Bug Fixes

- **setup**: Install into uv tool env instead of active venv
  ([`4169f60`](https://github.com/ksm0709/pkm/commit/4169f6065ef7c45b29fb3d21b202210de5d78f27))


## v1.1.0 (2026-04-05)

### Bug Fixes

- **release**: Use GH_TOKEN (PAT) to bypass branch protection
  ([`98bbdf6`](https://github.com/ksm0709/pkm/commit/98bbdf6011dcb53618cc1649ef74322cff9abb7f))

- **update**: Preserve [search] extras after reinstall
  ([`98bbdf6`](https://github.com/ksm0709/pkm/commit/98bbdf6011dcb53618cc1649ef74322cff9abb7f))

### Features

- Add pkm daily edit + sub-note structure
  ([`fa83053`](https://github.com/ksm0709/pkm/commit/fa83053f61ceba0ed462d6293d11ee2122e5e9ae))

- Add pkm vault open <name> for intuitive vault switching
  ([`ce7b30d`](https://github.com/ksm0709/pkm/commit/ce7b30da9ef2cc8a2fbb63971bc137c06d4be261))


## v1.0.0 (2026-04-05)

- Initial Release
