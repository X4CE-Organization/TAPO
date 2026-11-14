# TAPO for VS Code

Syntax highlighting, snippets and language configuration for the TAPO language.

## Install locally

Copy this folder into your VS Code extensions directory, for example:

```bash
cp -R editors/vscode ~/.vscode/extensions/tapo-language-0.0.1
```

Then reload VS Code and open any `.tapo` program or `.takg` library file. The extension contributes:

- `source.tapo` TextMate grammar (keywords, classes, aspects, interpolation,
  strings, operators, built-in types);
- language configuration (comments, brackets, auto-closing, indentation);
- snippets for classes, mixins, aspects, around advice, functions, lambdas,
  matches, loops, tests and pipelines.

## Package

If you have `vsce` installed:

```bash
cd editors/vscode
vsce package
code --install-extension tapo-language-0.0.1.vsix
```

MIT © 2026 X4CE.
