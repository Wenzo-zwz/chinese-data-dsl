---
name: chinese-data-dsl
description: Create, extend, validate, deploy, and use a Chinese-language data analysis DSL that translates business-readable Chinese instructions into executable Python for pandas DataFrame operations and NumPy array, matrix, random, and statistics operations. Use when the user asks for Chinese pandas, Chinese NumPy, DSL translation, auditable data-cleaning scripts that non-programmers can read, or packaging/deploying these workflows as a Codex skill on company computers.
---

# Chinese Data DSL

Use this skill to turn Chinese data-analysis steps into executable Python backed by pandas and NumPy. Keep the DSL small, auditable, and business-readable.

## Workflow

1. Read `references/syntax.md` when you need exact DSL syntax or examples.
2. Use `scripts/zhdata.py` as the canonical translator. Patch this script instead of rewriting the translator from scratch.
3. For company installation, dependency setup, offline wheel packaging, and smoke tests, read `references/deployment.md`.
4. For a new workflow, create a UTF-8 `.zd` script near the user's data file, then run:

```powershell
& "<python.exe>" scripts/zhdata.py path\to\script.zd
```

5. Use `--emit-python` before running unfamiliar data workflows so reviewers can inspect the generated Python.
6. Use `--output-python generated.py` when the translated Python should be saved.

## DSL Boundaries

Keep the language deliberately small and readable. Prefer one Chinese instruction per data operation. Do not add arbitrary Python execution syntax unless the user explicitly wants a less restricted scripting language.

Support two domains in one script:

- pandas table work: reading files, selecting columns, filtering, sorting, missing values, new columns, grouping, and saving.
- NumPy numeric work: arrays, matrices, generated ranges, random arrays, reshape, transpose, dot product, elementwise math, reductions, and `.npy` files.

Important constraints:

- DSL files must be UTF-8.
- Relative file paths in `.zd` scripts resolve relative to the `.zd` file.
- Table names, array names, and output variable names must be valid Python identifiers, such as `订单`, `A`, or `matrix_a`.
- `包含` is literal substring matching, not regular expression matching.
- `新增列` expressions support column names, numbers, quoted string literals, parentheses, and `+ - * /`. Reject unsupported characters instead of guessing.
- Generated code is straightforward pandas/NumPy Python and is executed with Python `exec`; inspect it with `--emit-python` for sensitive workflows.

## Implementation Notes

- Preserve generated Python as straightforward pandas/NumPy code so technical reviewers can audit it.
- Extend syntax by adding a `_compile_*` method to `ChineseDataCompiler`, then add an example to `references/syntax.md`.
- Validate changes by running `python -m unittest discover -s tests`, plus at least one pandas example and one NumPy example when changing execution behavior.
- Keep dependencies explicit in `requirements.txt`.
