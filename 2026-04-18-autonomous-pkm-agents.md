Metadata:
id: 2026-04-18-autonomous-pkm-agents
aliases: []
tags:
- pkm
- llm-agents
- security
source: '2026-04-18'

# Autonomous PKM Agents: Architecture and Risks

## Architectural Feasibility
- **Agentic Vault Maintenance over RAG**: Traditional RAG dynamically pulls information from vector databases but struggles to synthesize overarching concepts. The "LLM Wiki" paradigm (compile-first) is preferred, where background processes actively compile raw data into structured markdown pages (e.g., `mneia`, `llm-wiki-vault`, `localbrain`).
- **Local vs. Frontier APIs**: Local inference runtimes (Ollama, vLLM) ensure data privacy but often struggle with the complex reasoning required for deep Zettelkasten synthesis. Hybrid approaches are emerging, using fast local tools for indexing and frontier models for complex semantic routing via secure MCP bridges.

## Security Vulnerabilities
- **Indirect Prompt Injection**: Granting an autonomous LLM agent continuous read/write access to a local file system introduces critical risks. A compromised or malicious document can trigger an agent to silently exfiltrate sensitive data or execute unauthorized overwrites (e.g., CVE-2026-25253 for OpenClaw).
- **Required Mitigations**: 
  1. Never grant the daemon broad file system access.
  2. Enforce strict capability-based access controls and OS-level sandboxing (AppArmor, containerization) restricted to the vault directory.
  3. Establish an explicit user approval pipeline (a staging area) before allowing destructive modifications to core notes.


## Recent Enhancements (2026-04-19 Update)
- **Hierarchical Agent Scoping**: By introducing `AGENTS.md` across directory boundaries (root, cli, docs, etc.), we provide finer-grained control and context isolation, which inherently limits the blast radius of any individual agent's capabilities.
