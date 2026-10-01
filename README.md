# 🦊 Kitsune

> A local coding agent powered by Ollama, with project memory, repository tools, recovery, web search, and autonomous coding workflows.

Kitsune is a locally operated coding agent designed to work directly with a project on the user's machine. It can inspect repositories, reason about coding tasks, modify files, run commands, verify changes, maintain project memory, and recover from failed changes.

This repository contains the **partitioned architecture of the working Kitsune codebase**. The original single-file implementation has been separated into responsibility-oriented Python modules while keeping `kitsune.py` as the public entry point.

---

## ✨ What Kitsune Does

### 💬 Chat

Kitsune provides an interactive local chat mode backed by Ollama. Chat can work with the project context and can route requests toward coding or web-search workflows when appropriate.

### 🛠️ Build / Edit

The coding agent can:

- Explore a project
- Read relevant files
- Create and modify files
- Create directories
- Run project commands
- Work across multiple files
- Inspect the result of its changes
- Verify completed work

### 🐛 Fix

The fix workflow can investigate a project or a supplied error, identify the underlying problem, make a targeted correction, and verify the result.

### 🔍 Review

Kitsune can review a file or an entire project, with an optional review focus such as security or performance.

### 💡 Idea / Brainstorm

Kitsune includes an interactive idea and brainstorming workflow using the configured local model.

### 🧠 Project Memory

Kitsune maintains persistent project-related information outside the source tree, including:

- Project knowledge
- Architecture information
- Decisions
- Environment information
- Workspace/session state
- Coding attempt history

Project identity is preserved through a small `.kitsune_id` marker in the project directory.

### 🌐 Web Search

Kitsune can perform web searches through its web-search subsystem and provide retrieved information to the local agent when current external information is required.

### 📁 Repository Intelligence

The repository subsystem provides tools for:

- Repository tree generation
- File searching
- Repository indexing
- Symbol lookup
- Safe file reading and writing
- Local syntax checks

The symbol index supports multiple programming languages, including Python, JavaScript/JSX, TypeScript/TSX, Java, C#, Go, Rust, Ruby, and PHP.

### 🔄 Recovery

Kitsune includes recovery mechanisms for coding changes, including Git-based recovery points and internal checkpoints.

It can also inspect Git state, create commits, undo the last commit, add remotes, and push changes.

### 📦 Export

Project export functionality is included for creating ZIP archives of project contents.

---

## 🏗️ Architecture

The project keeps a small public entry point:

```text
kitsune.py
```

The implementation lives inside:

```text
kitsune_core/
```

The core is divided by responsibility rather than keeping the entire application inside one Python file.

```text
kitsune_core/
├── agent.py
├── agent_io.py
├── agent_protocol.py
├── attempts.py
├── brainstorm.py
├── chat.py
├── checkpoints.py
├── cli.py
├── commands.py
├── config.py
├── export_tests.py
├── foundation.py
├── git.py
├── memory_core.py
├── memory_types.py
├── migration.py
├── models.py
├── ollama.py
├── projects.py
├── recovery_git.py
├── registry.py
├── regression.py
├── repo.py
├── review.py
├── risk.py
├── sanity.py
├── startup.py
├── storage.py
└── web.py
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `agent.py` | Autonomous coding-agent execution |
| `agent_io.py` | Agent input/output handling |
| `agent_protocol.py` | Agent action protocol and response parsing |
| `attempts.py` | Coding attempt memory |
| `brainstorm.py` | Idea and brainstorming workflow |
| `chat.py` | Interactive chat workflow |
| `checkpoints.py` | Checkpoint storage and recovery data |
| `cli.py` | CLI entry and argument handling |
| `commands.py` | User-facing command implementations |
| `config.py` | Configuration loading and persistence |
| `export_tests.py` | Export and test-related utilities |
| `foundation.py` | Shared foundational utilities |
| `git.py` | Git operations |
| `memory_core.py` | Memory validation, loading, saving, and confidence handling |
| `memory_types.py` | Memory structures and project memory operations |
| `migration.py` | Legacy project-data migration |
| `models.py` | Model selection and model availability handling |
| `ollama.py` | Ollama communication and connectivity |
| `projects.py` | Project lifecycle and project resolution |
| `recovery_git.py` | Git-backed recovery operations |
| `registry.py` | Project registry management |
| `regression.py` | Regression and verification helpers |
| `repo.py` | Repository inspection and file operations |
| `review.py` | Code-review workflow |
| `risk.py` | Change-risk handling |
| `sanity.py` | Sanity and consistency checks |
| `startup.py` | Startup initialization and validation |
| `storage.py` | Kitsune storage paths and persistent storage |
| `web.py` | Web-search functionality |

Small modules are intentional where a distinct responsibility or dependency boundary exists.

---

## 💾 Persistent Storage

Kitsune keeps persistent runtime data separate from the project source code.

The core storage location is:

```text
~/.kitsune/
```

Its persistent areas include:

```text
~/.kitsune/
├── memory/
│   ├── knowledge/
│   ├── architecture/
│   ├── decisions/
│   ├── environment/
│   ├── workspace/
│   ├── archives/
│   └── checkpoints/
├── projects/
│   └── registry.json
└── logs/
    └── kitsune.log
```

The actual project source remains wherever the user places the project. Kitsune does not require its persistent memory and logs to be stored inside the source repository.

---

## 🤖 Local Model Runtime

Kitsune uses **Ollama** as its local model runtime.

The application communicates with the local Ollama service at:

```text
http://localhost:11434
```

The configured model can be selected through Kitsune's configuration and model-selection system. Different task roles can have their own model configuration, including chat, build, fix, review, idea, and routing roles.

---

## 📋 Available Commands

Kitsune exposes the following command workflows:

```text
build
fix
review
chat
idea
undo
memory
attempts
gc
index
```

The standard entry point remains:

```bash
python kitsune.py
```

For command-line usage, the individual workflows can also be invoked through the same entry point.

Example:

```bash
python kitsune.py build --dir "path/to/project" --goal "Add a login page"
```

---

## ⚙️ Requirements

- Windows, Linux, or another supported Python environment
- Python 3
- Ollama running locally
- A compatible Ollama model configured for Kitsune
- Python packages used by the application, including `requests` and the web-search dependency
- Git for Git-backed repository and recovery features

---

## 🔐 Local-First Design

Kitsune's model execution is designed around a local Ollama runtime rather than a required cloud API key.

Project files, persistent memory, configuration, checkpoints, and logs are handled locally by the application.

---

## 📜 Version

```text
0.1.0-ollama
```

This version represents the partitioned form of the existing Kitsune implementation. The partition separates its existing responsibilities into modules while retaining `kitsune.py` as the familiar launch point.
