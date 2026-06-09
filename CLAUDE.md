# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is currently a greenfield project. As of this writing it contains only `README.md` and this file — there is no source code, build tooling, dependency manifest, or test suite yet.

The project is intended to be an **investment dashboard with AI** ("投資 Ai"). The technology stack, architecture, and conventions have not been established.

## What to do here

Because nothing is scaffolded yet, the first substantive task in this repo will define its shape. When adding the initial code:

- After a stack is chosen (framework, language, package manager), **update this file** with the real build / lint / test / run commands and the architectural overview, replacing this placeholder guidance. Future Claude instances depend on this file being current.
- Document how to run a single test once a test runner exists.
- Record any non-obvious architecture (data sources for market/investment data, how AI features are wired in, auth, etc.) that requires reading multiple files to understand.

Do not invent commands or structure that don't exist in the repo — verify against the actual files before documenting them.

## Git workflow

- Develop on the feature branch you were assigned; create it locally if it doesn't exist.
- Push with `git push -u origin <branch-name>`.
- Do not open a pull request unless explicitly asked.
