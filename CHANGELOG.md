# CHANGELOG

<!-- version list -->

## v2.37.0 (2026-04-18)

### Chores

- **ask**: Switch default LLM model to gemini-3.1-flash-preview
  ([`e69e973`](https://github.com/ksm0709/pkm/commit/e69e973bbecc50c5835dea36a665147bac86fcfe))

### Features

- **ask**: Auto model selection and fallback with curated list
  ([`f6f0bed`](https://github.com/ksm0709/pkm/commit/f6f0beddae9ae8d561b02dc80a3c7d7294b79d32))


## v2.36.0 (2026-04-18)

### Features

- **ask**: Show configured model when no query is provided
  ([`93d350f`](https://github.com/ksm0709/pkm/commit/93d350fff1e43eb86e89c0684d1aa36f4f839be4))


## v2.35.0 (2026-04-18)

### Features

- **ask**: Support configurable LLM models via CLI and config
  ([`9ab01b9`](https://github.com/ksm0709/pkm/commit/9ab01b958bbe30c117a841004e414b622e1ce9ae))


## v2.34.0 (2026-04-18)

### Features

- **ask**: Validate litellm API keys before calling daemon
  ([`2db3974`](https://github.com/ksm0709/pkm/commit/2db3974f1500def008e4edd50ed39bf2a05d50af))


## v2.33.1 (2026-04-18)

### Bug Fixes

- **mcp**: Remove ctx from pkm_ask tool and update docs
  ([`b051cfd`](https://github.com/ksm0709/pkm/commit/b051cfd1bb49ad002991b142972e926d5bddec2d))

### Chores

- Remove .skip-hook
  ([`87b83f7`](https://github.com/ksm0709/pkm/commit/87b83f7f3a5285c256ba3c88a85c1861eca2d640))

### Documentation

- **pkm**: Document split architecture daemon and ask command
  ([`23169a4`](https://github.com/ksm0709/pkm/commit/23169a463383bc0133889a0aac7897f9133342aa))


## v2.33.0 (2026-04-18)

### Bug Fixes

- Remove unused variable include_graph_context in daemon.py
  ([`a17a31b`](https://github.com/ksm0709/pkm/commit/a17a31bfbea140ca5cf100811727802084742722))

- **mcp**: Update test assertion for tools count and fix type hints
  ([`cced391`](https://github.com/ksm0709/pkm/commit/cced39135009edfed2a68beb70c6ef2b95b741f1))

### Chores

- Add documentation update reminder to quality hooks
  ([`cdea52b`](https://github.com/ksm0709/pkm/commit/cdea52ba208bf0724e3a93523cbeb20ed9cb3af4))

### Documentation

- Restructure CLI and MCP server documentation
  ([`726a675`](https://github.com/ksm0709/pkm/commit/726a67576cadc5a78721f985000d4f14323c9a10))

### Features

- Add ask command for natural language vault queries
  ([`e770687`](https://github.com/ksm0709/pkm/commit/e770687ab34b9e2eca55c7b53dc0c4206875aef0))


## v2.32.0 (2026-04-18)

### Features

- **pkm**: Replace vault cd with vault edit and change where output for alias use
  ([`d1c20a3`](https://github.com/ksm0709/pkm/commit/d1c20a340f31ac89d84a6b6fea63cc5175a8e307))


## v2.31.0 (2026-04-18)

### Bug Fixes

- **pkm**: Correct graph path and remove ast load in daemon
  ([`7887122`](https://github.com/ksm0709/pkm/commit/7887122ab80ed3bd256eb5e06f144f63a7d43a42))

- **pkm**: Create daemon log directory before logging to prevent CI FileNotFoundError
  ([`a3af880`](https://github.com/ksm0709/pkm/commit/a3af88092ede9770885e70b7cac8d260e1927194))

- **pkm**: Defer numpy import until after transformer check
  ([`aafe2fa`](https://github.com/ksm0709/pkm/commit/aafe2fa4856f69ab70863cb5785fdb271c013dc4))

- **pkm**: Flatten multidimensional embeddings in semantic search
  ([`64781af`](https://github.com/ksm0709/pkm/commit/64781af78c7e45af478d792e391179f50a55bebe))

- **pkm**: Handle dict response format in daemon search
  ([`f3ce04b`](https://github.com/ksm0709/pkm/commit/f3ce04bc38b128053f9c2d460e74c884b65de6ea))

- **pkm**: Move ast.db and graph.json from .context/ to pkm_dir root
  ([`df61529`](https://github.com/ksm0709/pkm/commit/df615294333794b853c5dc8fab3c7c8f1a2ff5b6))

- **pkm**: Prevent subprocess Popen from hanging the shell on stdin
  ([`ee01b2c`](https://github.com/ksm0709/pkm/commit/ee01b2ca293bf9631aafbfc93cd9a9bf8ccc3c5e))

- **pkm**: Remove unused mtime variables to pass linter
  ([`adeab21`](https://github.com/ksm0709/pkm/commit/adeab219aee4c947596c535c750a9f291c203ab9))

- **pkm**: Resolve validator rejections for semantic split, safe auto-link, and daemon security
  ([`5a0057c`](https://github.com/ksm0709/pkm/commit/5a0057c174b9779b264e566a1c247eb7457abeea))

### Code Style

- **pkm**: Apply formatter fixes to changelog.py
  ([`6c5784b`](https://github.com/ksm0709/pkm/commit/6c5784b590f1361b1b809850e15684879f76935c))

- **pkm**: Apply formatter to config command
  ([`aef7bc4`](https://github.com/ksm0709/pkm/commit/aef7bc4fe9e3223ca4c2fdd6d53946194457d11a))

- **pkm**: Apply formatter to search engine and commands
  ([`c1f614e`](https://github.com/ksm0709/pkm/commit/c1f614ec63e3fbbabe422f7068a0c0d2b5e1eb5c))

- **pkm**: Apply formatter to vault commands and tests
  ([`70e2623`](https://github.com/ksm0709/pkm/commit/70e26231d949e80960e5bdcf9cfa3f681c189725))

- **pkm**: Apply linter and formatter fixes
  ([`23fce8b`](https://github.com/ksm0709/pkm/commit/23fce8b477fb31e1d23ac80c5667f8c5b216481d))

### Features

- **pkm**: Add cd command to start a shell in the vault directory
  ([`64c520e`](https://github.com/ksm0709/pkm/commit/64c520e02c26bfc302962a1a9d45fdc6aeedd17f))

- **pkm**: Add changelog parser and apply code formatting to search engine
  ([`1139077`](https://github.com/ksm0709/pkm/commit/11390775657308d933f31c65444ca3f1d17c2e3e))

- **pkm**: Dynamically show all available configs in config list
  ([`76fe34f`](https://github.com/ksm0709/pkm/commit/76fe34fe305783c196a6750185bcacde30d474fe))

- **pkm**: Implement incremental FAISS embedding cache via vector.db
  ([`2197057`](https://github.com/ksm0709/pkm/commit/2197057037476877f3fd302ef7209073b4bea78a))

- **pkm**: Show changelog on --version and update commands
  ([`f0ac01a`](https://github.com/ksm0709/pkm/commit/f0ac01a01e245fd5aa68169319082780ce6c6f1e))

- **pkm**: Verbose success logs for all indexing components
  ([`56d4729`](https://github.com/ksm0709/pkm/commit/56d4729bfeebeba7618b5e93bb5105df583a7993))

### Refactoring

- **pkm**: Remove deprecated agent command and tests
  ([`c3d1b16`](https://github.com/ksm0709/pkm/commit/c3d1b16bb489b1dba9b009ebaa7968a92809cb15))

### Testing

- **pkm**: Add regression tests for deferred numpy import fallback
  ([`bcc5358`](https://github.com/ksm0709/pkm/commit/bcc5358e548ec0abdb07254745f0d79609bb67a3))


## v2.30.0 (2026-04-18)

### Features

- **pkm**: Implement auto-link, split, and graph traversal context
  ([`e59334d`](https://github.com/ksm0709/pkm/commit/e59334ddb12370fc8d6061285a09f740a0895725))


## v2.29.0 (2026-04-18)

### Chores

- Add mistletoe test scripts for parser research
  ([`10ce33e`](https://github.com/ksm0709/pkm/commit/10ce33e603127dad915e29ae39708fa44ed7e2f9))

- Add test probes and dummy graph for graphify research
  ([`d6741b4`](https://github.com/ksm0709/pkm/commit/d6741b4c4554a68517227a4f58071f14b3bc3677))

### Features

- **pkm**: Implement incremental AST caching and daemon graph integration
  ([`76242f3`](https://github.com/ksm0709/pkm/commit/76242f33c74e3f28bfadac25b644fb9668dd663f))

### Refactoring

- **pkm**: Clean up unused workflows and simplify core loops in plugin skill
  ([`9da3506`](https://github.com/ksm0709/pkm/commit/9da3506664be215bff76c160876bc6f5b96851aa))


## v2.28.5 (2026-04-16)

### Bug Fixes

- Clean up stop hook output, suppress logs on success
  ([`08359ff`](https://github.com/ksm0709/pkm/commit/08359ffa8a47f34c5743add6632ace1eb9d6392f))


## v2.28.4 (2026-04-16)

### Bug Fixes

- Add pwd fallback for non-git project stop hook path
  ([`cf8a1ef`](https://github.com/ksm0709/pkm/commit/cf8a1efddc7fee0139e5409539524f1da8faa71f))

- Use absolute path for Stop hook, fix skill sync path
  ([`48c7867`](https://github.com/ksm0709/pkm/commit/48c7867454e934bb6d9eb8fb6d0bcc081971f127))


## v2.28.3 (2026-04-16)

### Bug Fixes

- Update skill source path after skill/ → plugin/skills/pkm/ move
  ([`93fb400`](https://github.com/ksm0709/pkm/commit/93fb40036f404001ca60efe853c53fbfd4c47cb4))


## v2.28.2 (2026-04-16)

### Bug Fixes

- Move semantic-release config to repo root, remove stale mcp extra probe
  ([`8d56d0c`](https://github.com/ksm0709/pkm/commit/8d56d0c3f06a514654a07c1baaec2c94cefccde5))


## v2.28.0 (2026-04-16)

### Features

- Auto-merge daily notes on vault unset, remove stale cli/.pkm
  ([`1301b67`](https://github.com/ksm0709/pkm/commit/1301b6710b97852243fe77fc11563e6dc3e9c1b0))


## v2.27.0 (2026-04-16)

### Features

- Default all CLI output to JSON, add turn-start context injection
  ([`1404fa0`](https://github.com/ksm0709/pkm/commit/1404fa084286ce5dd4c4dafaf7dabd4ddb986b8d))


## v2.26.1 (2026-04-16)

### Bug Fixes

- Preserve all installed extras during pkm update
  ([`958b602`](https://github.com/ksm0709/pkm/commit/958b60265a9a4ea4d7e57a1318b4a5e5b83be946))

### Refactoring

- Generalize agent-specific names in examples
  ([`6272bea`](https://github.com/ksm0709/pkm/commit/6272bea12ab14012bb738ff2716fd1db4abe159b))

- Remove zeroclaw references from MCP server docstrings
  ([`bea5557`](https://github.com/ksm0709/pkm/commit/bea5557901f9652a40e639a732b26bc70aa24f9c))


## v2.26.0 (2026-04-15)

### Features

- Add MCP server for zeroclaw agent integration
  ([`5899fa3`](https://github.com/ksm0709/pkm/commit/5899fa3462521abd8366a3165eb70d6e220344d0))


## v2.25.0 (2026-04-15)

### Features

- Optimize pkm search by wiring daemon as primary search path
  ([`ad60e03`](https://github.com/ksm0709/pkm/commit/ad60e0335068e11eccf80788d309bb24b6adf0ab))


## v2.24.0 (2026-04-14)

### Features

- Add importance scoring guidelines to session start hook and memory-store skill
  ([`d0c1979`](https://github.com/ksm0709/pkm/commit/d0c1979f8fd243d99516d82245753fc870f89a4a))


## v2.23.0 (2026-04-14)

### Features

- Add data management, streamline hooks, auto-consolidate on daemon shutdown
  ([`7a63b11`](https://github.com/ksm0709/pkm/commit/7a63b1144a07f34662c07d191d230e5d8c958952))


## v2.22.0 (2026-04-13)

### Features

- **cli**: Add pkm daemon command group for daemon management
  ([`4861184`](https://github.com/ksm0709/pkm/commit/486118460e9ee5ef6e708c6d6a6854e53df74506))


## v2.21.0 (2026-04-11)

### Chores

- Automated quality gate commit from stop hook
  ([`8ee5b08`](https://github.com/ksm0709/pkm/commit/8ee5b08e7da5855512bacae7025f185e7dc527b3))

- Setup OpenCode Stop hook for quality gate enforcement
  ([`e638f0b`](https://github.com/ksm0709/pkm/commit/e638f0b16b631769ae053bffe9b816f83c15f6cc))

- **hooks**: Clarify stop hook background wait guidance
  ([`2255c48`](https://github.com/ksm0709/pkm/commit/2255c48e28e50c918f05935940bb0d7609c0f4b3))

### Documentation

- Enhance stop hook to instruct the agent to check for remaining tasks and wait 30s before
  committing
  ([`89673a3`](https://github.com/ksm0709/pkm/commit/89673a3f8197c79056c54dcbab0d2105a7d65064))

### Features

- Add robust logging to daemon server
  ([`a9da1a9`](https://github.com/ksm0709/pkm/commit/a9da1a950a6af544c1a8183adba2b705c85ae714))

### Refactoring

- Offload note indexing and dedup to daemon server
  ([`f3bfcb7`](https://github.com/ksm0709/pkm/commit/f3bfcb72f5a11304cdba3b7cd3b88824291f2559))

- Simplify Stop hook to run only static analysis (lint, test) and omit agentic reviews
  ([`e1c342a`](https://github.com/ksm0709/pkm/commit/e1c342ac14274672e907b83df4ba32f823a7288e))

### Testing

- **vault**: Align unset command tests with project-based config
  ([`d032d09`](https://github.com/ksm0709/pkm/commit/d032d0994798227129713272f99e8909e3c05a5e))


## v2.20.0 (2026-04-11)

### Features

- Implement persistent python ML daemon for fast semantic search hooks
  ([`38f24a7`](https://github.com/ksm0709/pkm/commit/38f24a74cafa2a8e82d20618ce36e004c5042acc))


## v2.19.0 (2026-04-11)

### Features

- **daily**: Simplify add output to single timestamp line
  ([`b4ca4aa`](https://github.com/ksm0709/pkm/commit/b4ca4aa13698180f7253bd9e00794b3cab952bf7))

- **hooks**: Auto-install Codex hooks by merging into ~/.codex/hooks.json
  ([`1fc16a3`](https://github.com/ksm0709/pkm/commit/1fc16a316fe93e164b501ee9b908f6d3840e79d7))

- **hooks**: Output JSON format for opencode omo plugin
  ([`f01c1fc`](https://github.com/ksm0709/pkm/commit/f01c1fc4e97fd587f028adaa267fb2da55397239))

### Refactoring

- **hooks**: Reduce duplication in hook messages
  ([`8224251`](https://github.com/ksm0709/pkm/commit/8224251c98b6e60b92129f890361f0da22ef0ed1))

### Testing

- **hooks**: Fix failing hook tests after output format changes
  ([`e43c021`](https://github.com/ksm0709/pkm/commit/e43c02181ede70e42586b0b7ef667121c7b743e3))


## v2.18.0 (2026-04-10)

### Features

- Clean turn-start/end injections and add hook debug mode
  ([`1fdefe2`](https://github.com/ksm0709/pkm/commit/1fdefe2d8abeccc9a38ab0f944825e2eaea5fbb8))


## v2.17.0 (2026-04-10)

### Bug Fixes

- Create .claude dir and update tests for settings.json write behavior
  ([`acbd097`](https://github.com/ksm0709/pkm/commit/acbd0971aae20613427e178ec49d2c92aff16b8a))

### Features

- Hook setup writes to settings.json; migrate renamed to remove
  ([`00bff98`](https://github.com/ksm0709/pkm/commit/00bff9824ab4eb9dcf5cc4bb730185f6312174af))


## v2.16.0 (2026-04-10)

### Features

- Hook setup without --tool installs all agents; vault no auto-create
  ([`507a2a5`](https://github.com/ksm0709/pkm/commit/507a2a5e2d344e216323133343d8fd2fdbc44d88))


## v2.15.0 (2026-04-10)

### Bug Fixes

- Add hook to VAULT_FREE_COMMANDS and lazy-load vault in run_hook
  ([`66a081e`](https://github.com/ksm0709/pkm/commit/66a081eacc3c0da1a603559673a1793d4bf30d8a))

### Documentation

- Update hook injection guide and skill docs for daily add --sub
  ([`0a93466`](https://github.com/ksm0709/pkm/commit/0a93466bd87e334ae6f4939eec9145dc516e0439))

### Features

- Add daily add --sub and wikilink injection to daily edit --sub
  ([`f6b74a2`](https://github.com/ksm0709/pkm/commit/f6b74a23161f092f7faa61a208de99df98c5c9c3))

- Add intelligent hook plugin system with hook isolation and Phase 2 intelligence
  ([`0c7e67e`](https://github.com/ksm0709/pkm/commit/0c7e67e99120168332549878f50dfe896fa60219))


## v2.14.0 (2026-04-09)

### Chores

- Add pkm-agent smoke check (pkm daily add integration test)
  ([`812c674`](https://github.com/ksm0709/pkm/commit/812c674f1bf9d32990e9ea848b927b4675dd3630))

### Features

- Add write-time dedup, dynamic context injection, and consolidation trigger
  ([`398dd09`](https://github.com/ksm0709/pkm/commit/398dd09e953fa05de593a4499fee27b53f493996))


## v2.13.1 (2026-04-09)

### Bug Fixes

- Address security review findings in hook.py
  ([`8209cb3`](https://github.com/ksm0709/pkm/commit/8209cb3c7f1c033c2af84d9c38db4804982ff065))

### Chores

- Add smoke checks (tests/lint/format), fix remaining lint issues
  ([`6a7da85`](https://github.com/ksm0709/pkm/commit/6a7da855031f93cbeaa2c69301e98af86bbbd9e4))

### Code Style

- Apply ruff lint and format fixes
  ([`78aa615`](https://github.com/ksm0709/pkm/commit/78aa615fabb0a86dd85f138a7444da6bced07405))


## v2.13.0 (2026-04-09)

### Features

- Hook refactor, JSON-first search/note output, agent-friendly UX
  ([`ea2ea5f`](https://github.com/ksm0709/pkm/commit/ea2ea5f0b62809c70999894c4baf47488a9f333d))


## v2.12.1 (2026-04-06)

### Bug Fixes

- Python 3.10 tomllib compat, add vault where command, vault context guide
  ([`51a79cd`](https://github.com/ksm0709/pkm/commit/51a79cdab361d66643312bf31a7e64e26fa4aea1))


## v2.12.0 (2026-04-06)

### Features

- Add pkm vault setup command for subdirectory vault declaration
  ([`1ea5177`](https://github.com/ksm0709/pkm/commit/1ea517763dee0aae915c2d2d1081b608bbc480f2))


## v2.11.0 (2026-04-06)

### Features

- **skill**: Add command descriptions and remove dream workflow
  ([`2b3e7f1`](https://github.com/ksm0709/pkm/commit/2b3e7f1dc26f30f67ec551fd4cc2bbabdf12505f))


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
