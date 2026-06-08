from __future__ import annotations

import argparse
import ast
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DSLParseError(Exception):
    pass


@dataclass
class CompileResult:
    code: str
    lines: list[str]


class ChineseDataCompiler:
    """Translate Chinese pandas and NumPy DSL commands into Python."""

    OPS = {
        "大于等于": ">=",
        "小于等于": "<=",
        "不等于": "!=",
        "大于": ">",
        "小于": "<",
        "等于": "==",
    }

    AGGS = {
        "求和": "sum",
        "平均": "mean",
        "计数": "count",
        "最大": "max",
        "最小": "min",
    }

    NP_REDUCE = {
        "求和": "sum",
        "求平均": "mean",
        "求最大": "max",
        "求最小": "min",
        "求标准差": "std",
        "求方差": "var",
        "求中位数": "median",
    }

    NP_BINARY = {
        "加": "+",
        "减": "-",
        "乘": "*",
        "除": "/",
    }

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path.cwd()
        self.current_table: str | None = None
        self.lines: list[str] = [
            "import numpy as np",
            "import pandas as pd",
            "",
        ]

    def compile(self, source: str) -> CompileResult:
        for line_no, raw_line in enumerate(source.splitlines(), start=1):
            line = self._strip_comment(raw_line).strip()
            if not line:
                continue
            try:
                self._compile_line(line)
            except DSLParseError as exc:
                raise DSLParseError(f"第 {line_no} 行无法解析：{line}\n原因：{exc}") from exc
        return CompileResult(code="\n".join(self.lines) + "\n", lines=self.lines)

    def _compile_line(self, line: str) -> None:
        compilers = [
            self._compile_read_csv,
            self._compile_read_excel,
            self._compile_use_table,
            self._compile_select,
            self._compile_filter,
            self._compile_sort,
            self._compile_group_agg,
            self._compile_rename,
            self._compile_drop_na,
            self._compile_fill_na,
            self._compile_new_column,
            self._compile_head,
            self._compile_save_csv,
            self._compile_save_excel,
            self._compile_np_seed,
            self._compile_np_array,
            self._compile_np_zeros_ones,
            self._compile_np_arange,
            self._compile_np_linspace,
            self._compile_np_random,
            self._compile_np_random_int,
            self._compile_np_load,
            self._compile_np_save,
            self._compile_np_reshape,
            self._compile_np_transpose,
            self._compile_np_dot,
            self._compile_np_reduce,
            self._compile_np_binary,
            self._compile_print,
        ]
        for compiler in compilers:
            if compiler(line):
                return
        raise DSLParseError("未知指令")

    # pandas DSL

    def _compile_read_csv(self, line: str) -> bool:
        match = re.fullmatch(r'读取CSV\s+(.+?)\s+为\s+(\w+)', line, re.IGNORECASE)
        if not match:
            return False
        path, table = match.groups()
        table = self._identifier(table, "表名")
        self.lines.append(f"{table} = pd.read_csv({self._path_literal(path)})")
        self.current_table = table
        return True

    def _compile_read_excel(self, line: str) -> bool:
        match = re.fullmatch(
            r'读取(?:EXCEL|Excel|excel)\s+(.+?)\s+为\s+(\w+)(?:\s+工作表\s+(.+))?',
            line,
        )
        if not match:
            return False
        path, table, sheet = match.groups()
        table = self._identifier(table, "表名")
        args = [self._path_literal(path)]
        if sheet:
            args.append(f"sheet_name={self._value_literal(sheet)}")
        self.lines.append(f"{table} = pd.read_excel({', '.join(args)})")
        self.current_table = table
        return True

    def _compile_use_table(self, line: str) -> bool:
        match = re.fullmatch(r'(?:使用|设当前为)\s+(\w+)', line)
        if not match:
            return False
        self.current_table = self._identifier(match.group(1), "表名")
        self.lines.append(f"# 当前表：{self.current_table}")
        return True

    def _compile_select(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?选择\s+列\s+(.+)', line)
        if not match:
            return False
        table, columns_text = match.groups()
        target = self._table(table)
        columns = self._parse_list(columns_text)
        self.lines.append(f"{target} = {target}.loc[:, {columns!r}]")
        return True

    def _compile_filter(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?筛选\s+(.+?)\s+(大于等于|小于等于|不等于|大于|小于|等于|包含)\s+(.+)', line)
        if not match:
            return False
        table, column, op, value = match.groups()
        target = self._table(table)
        column_name = self._clean_name(column)
        if op == "包含":
            self.lines.append(
                f"{target} = {target}[{target}[{column_name!r}].astype(str).str.contains({self._value_literal(value)}, na=False, regex=False)]"
            )
        else:
            self.lines.append(f"{target} = {target}[{target}[{column_name!r}] {self.OPS[op]} {self._value_literal(value)}]")
        return True

    def _compile_sort(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?按\s+(.+?)\s+排序(?:\s+(升序|降序))?', line)
        if not match:
            return False
        table, column, order = match.groups()
        target = self._table(table)
        ascending = order != "降序"
        self.lines.append(f"{target} = {target}.sort_values(by={self._clean_name(column)!r}, ascending={ascending})")
        return True

    def _compile_group_agg(self, line: str) -> bool:
        match = re.fullmatch(
            r'(?:从\s+(\w+)\s+)?按\s+(.+?)\s+分组\s+汇总\s+(.+?)\s+(求和|平均|计数|最大|最小)(?:\s+为\s+(.+))?',
            line,
        )
        if not match:
            return False
        table, group_text, value_column, agg, alias = match.groups()
        target = self._table(table)
        group_cols = self._parse_columns(group_text)
        value_col = self._clean_name(value_column)
        output_col = self._clean_name(alias) if alias else value_col
        group_expr = group_cols[0] if len(group_cols) == 1 else group_cols
        named_agg = {output_col: (value_col, self.AGGS[agg])}
        self.lines.append(f"{target} = {target}.groupby({group_expr!r}, as_index=False).agg(**{named_agg!r})")
        return True

    def _compile_rename(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?重命名列\s+(.+?)\s+为\s+(.+)', line)
        if not match:
            return False
        table, old, new = match.groups()
        target = self._table(table)
        self.lines.append(f"{target} = {target}.rename(columns={{{self._clean_name(old)!r}: {self._clean_name(new)!r}}})")
        return True

    def _compile_drop_na(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?删除空值(?:\s+列\s+(.+))?', line)
        if not match:
            return False
        table, column = match.groups()
        target = self._table(table)
        if column:
            self.lines.append(f"{target} = {target}.dropna(subset=[{self._clean_name(column)!r}])")
        else:
            self.lines.append(f"{target} = {target}.dropna()")
        return True

    def _compile_fill_na(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?填充空值\s+列\s+(.+?)\s+为\s+(.+)', line)
        if not match:
            return False
        table, column, value = match.groups()
        target = self._table(table)
        col = self._clean_name(column)
        self.lines.append(f"{target}[{col!r}] = {target}[{col!r}].fillna({self._value_literal(value)})")
        return True

    def _compile_new_column(self, line: str) -> bool:
        match = re.fullmatch(r'(?:从\s+(\w+)\s+)?新增列\s+(.+?)\s*=\s*(.+)', line)
        if not match:
            return False
        table, column, expression = match.groups()
        target = self._table(table)
        py_expr = self._compile_table_expression(expression, target)
        self.lines.append(f"{target}[{self._clean_name(column)!r}] = {py_expr}")
        return True

    def _compile_head(self, line: str) -> bool:
        match = re.fullmatch(r'(?:查看|显示)前\s*(\d+)\s*行(?:\s+(\w+))?', line)
        if not match:
            return False
        count, table = match.groups()
        target = self._table(table)
        self.lines.append(f"print({target}.head({int(count)}))")
        return True

    def _compile_save_csv(self, line: str) -> bool:
        match = re.fullmatch(r'(?:保存CSV|保存为CSV)\s+(.+?)(?:\s+从\s+(\w+))?', line, re.IGNORECASE)
        if not match:
            return False
        path, table = match.groups()
        target = self._table(table)
        self.lines.append(f"{target}.to_csv({self._path_literal(path)}, index=False, encoding='utf-8-sig')")
        return True

    def _compile_save_excel(self, line: str) -> bool:
        match = re.fullmatch(r'(?:保存EXCEL|保存Excel|保存excel|保存为EXCEL|保存为Excel|保存为excel)\s+(.+?)(?:\s+从\s+(\w+))?', line)
        if not match:
            return False
        path, table = match.groups()
        target = self._table(table)
        self.lines.append(f"{target}.to_excel({self._path_literal(path)}, index=False)")
        return True

    # NumPy DSL

    def _compile_np_seed(self, line: str) -> bool:
        match = re.fullmatch(r'设置随机种子\s+(\d+)', line)
        if not match:
            return False
        self.lines.append(f"np.random.seed({int(match.group(1))})")
        return True

    def _compile_np_array(self, line: str) -> bool:
        match = re.fullmatch(r'创建(?:数组|矩阵)\s+(\w+)\s*=\s*(.+)', line)
        if not match:
            return False
        name, value = match.groups()
        name = self._identifier(name, "数组名")
        self.lines.append(f"{name} = np.array({self._python_literal(value)})")
        return True

    def _compile_np_zeros_ones(self, line: str) -> bool:
        match = re.fullmatch(r'生成(零数组|一数组)\s+(\w+)\s+形状\s+(.+)', line)
        if not match:
            return False
        kind, name, shape = match.groups()
        name = self._identifier(name, "数组名")
        func = "zeros" if kind == "零数组" else "ones"
        self.lines.append(f"{name} = np.{func}({self._shape_literal(shape)})")
        return True

    def _compile_np_arange(self, line: str) -> bool:
        match = re.fullmatch(r'生成等差数组\s+(\w+)\s+从\s+(.+?)\s+到\s+(.+?)(?:\s+步长\s+(.+))?', line)
        if not match:
            return False
        name, start, stop, step = match.groups()
        name = self._identifier(name, "数组名")
        args = [self._number_literal(start), self._number_literal(stop)]
        if step is not None:
            args.append(self._number_literal(step))
        self.lines.append(f"{name} = np.arange({', '.join(args)})")
        return True

    def _compile_np_linspace(self, line: str) -> bool:
        match = re.fullmatch(r'生成线性数组\s+(\w+)\s+从\s+(.+?)\s+到\s+(.+?)\s+个数\s+(\d+)', line)
        if not match:
            return False
        name, start, stop, count = match.groups()
        name = self._identifier(name, "数组名")
        self.lines.append(f"{name} = np.linspace({self._number_literal(start)}, {self._number_literal(stop)}, {int(count)})")
        return True

    def _compile_np_random(self, line: str) -> bool:
        match = re.fullmatch(r'生成随机数组\s+(\w+)\s+形状\s+(.+)', line)
        if not match:
            return False
        name, shape = match.groups()
        name = self._identifier(name, "数组名")
        self.lines.append(f"{name} = np.random.rand(*{self._shape_literal(shape)})")
        return True

    def _compile_np_random_int(self, line: str) -> bool:
        match = re.fullmatch(r'生成随机整数\s+(\w+)\s+从\s+(.+?)\s+到\s+(.+?)\s+形状\s+(.+)', line)
        if not match:
            return False
        name, low, high, shape = match.groups()
        name = self._identifier(name, "数组名")
        high_value = self._parse_scalar(high)
        if not isinstance(high_value, int):
            raise DSLParseError("随机整数的上界需要是整数")
        self.lines.append(
            f"{name} = np.random.randint({self._number_literal(low)}, {high_value + 1}, size={self._shape_literal(shape)})"
        )
        return True

    def _compile_np_load(self, line: str) -> bool:
        match = re.fullmatch(r'读取数组\s+(.+?)\s+为\s+(\w+)', line)
        if not match:
            return False
        path, name = match.groups()
        name = self._identifier(name, "数组名")
        self.lines.append(f"{name} = np.load({self._path_literal(path)})")
        return True

    def _compile_np_save(self, line: str) -> bool:
        match = re.fullmatch(r'保存数组\s+(.+?)\s+从\s+(\w+)', line)
        if not match:
            return False
        path, name = match.groups()
        name = self._identifier(name, "数组名")
        self.lines.append(f"np.save({self._path_literal(path)}, {name})")
        return True

    def _compile_np_reshape(self, line: str) -> bool:
        match = re.fullmatch(r'数组\s+(\w+)\s+重塑\s+为\s+(.+?)(?:\s+保存为\s+(\w+))?', line)
        if not match:
            return False
        name, shape, output = match.groups()
        name = self._identifier(name, "数组名")
        target = self._identifier(output, "数组名") if output else name
        self.lines.append(f"{target} = {name}.reshape({self._shape_literal(shape)})")
        return True

    def _compile_np_transpose(self, line: str) -> bool:
        match = re.fullmatch(r'转置\s+(\w+)\s+为\s+(\w+)', line)
        if not match:
            return False
        source, output = match.groups()
        source = self._identifier(source, "数组名")
        output = self._identifier(output, "数组名")
        self.lines.append(f"{output} = np.transpose({source})")
        return True

    def _compile_np_dot(self, line: str) -> bool:
        match = re.fullmatch(r'矩阵\s+(\w+)\s+点乘\s+(\w+)\s+为\s+(\w+)', line)
        if not match:
            return False
        left, right, output = match.groups()
        left = self._identifier(left, "矩阵名")
        right = self._identifier(right, "矩阵名")
        output = self._identifier(output, "矩阵名")
        self.lines.append(f"{output} = np.dot({left}, {right})")
        return True

    def _compile_np_reduce(self, line: str) -> bool:
        match = re.fullmatch(r'对\s+(\w+)\s+(求和|求平均|求最大|求最小|求标准差|求方差|求中位数)(?:\s+按轴\s+(\d+))?\s+为\s+(\w+)', line)
        if not match:
            return False
        source, action, axis, output = match.groups()
        source = self._identifier(source, "数组名")
        output = self._identifier(output, "数组名")
        axis_arg = "" if axis is None else f", axis={int(axis)}"
        self.lines.append(f"{output} = np.{self.NP_REDUCE[action]}({source}{axis_arg})")
        return True

    def _compile_np_binary(self, line: str) -> bool:
        match = re.fullmatch(r'数组\s+(\w+)\s+(加|减|乘|除)\s+(.+?)\s+为\s+(\w+)', line)
        if not match:
            return False
        left, op, right, output = match.groups()
        left = self._identifier(left, "数组名")
        output = self._identifier(output, "数组名")
        self.lines.append(f"{output} = {left} {self.NP_BINARY[op]} {self._numpy_operand(right)}")
        return True

    def _compile_print(self, line: str) -> bool:
        match = re.fullmatch(r'(?:打印|显示)\s+(\w+)', line)
        if not match:
            return False
        name = self._identifier(match.group(1), "变量名")
        self.lines.append(f"print({name})")
        return True

    # Helpers

    def _table(self, explicit: str | None = None) -> str:
        table = explicit or self.current_table
        if not table:
            raise DSLParseError("还没有当前表，请先使用“读取CSV ... 为 表名”")
        table = self._identifier(table, "表名")
        self.current_table = table
        return table

    def _path_literal(self, text: str) -> str:
        value = self._parse_scalar(text)
        if not isinstance(value, str):
            raise DSLParseError("文件路径需要用引号包起来，例如 \"订单.csv\"")
        path = Path(value)
        if not path.is_absolute():
            path = self.base_dir / path
        return repr(str(path))

    def _value_literal(self, text: str) -> str:
        return repr(self._parse_scalar(text))

    def _number_literal(self, text: str) -> str:
        value = self._parse_scalar(text)
        if not isinstance(value, int | float):
            raise DSLParseError(f"需要数字，但得到：{text}")
        return repr(value)

    def _python_literal(self, text: str) -> str:
        try:
            value = ast.literal_eval(text.strip())
        except (ValueError, SyntaxError) as exc:
            raise DSLParseError(f"需要 Python 字面量，例如 [1, 2, 3] 或 [[1, 2], [3, 4]]：{text}") from exc
        return repr(value)

    def _shape_literal(self, text: str) -> str:
        value = ast.literal_eval(text.strip())
        if isinstance(value, int):
            return f"({value},)"
        if isinstance(value, list):
            value = tuple(value)
        if not isinstance(value, tuple) or not value or not all(isinstance(item, int) for item in value):
            raise DSLParseError("形状需要是整数或整数列表，例如 3 或 [2, 3]")
        return repr(value)

    def _numpy_operand(self, text: str) -> str:
        cleaned = text.strip()
        if re.fullmatch(r'\w+', cleaned) and not re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
            return self._identifier(cleaned, "数组名")
        parsed = self._parse_scalar(cleaned)
        if isinstance(parsed, int | float | str) and cleaned in {str(parsed), repr(parsed)}:
            return repr(parsed)
        return self._python_literal(cleaned)

    def _parse_scalar(self, text: str):
        cleaned = text.strip()
        try:
            return ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            pass
        if re.fullmatch(r'-?\d+', cleaned):
            return int(cleaned)
        if re.fullmatch(r'-?\d+\.\d+', cleaned):
            return float(cleaned)
        return self._clean_name(cleaned)

    def _parse_list(self, text: str) -> list[str]:
        cleaned = text.strip()
        try:
            value = ast.literal_eval(cleaned)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return value
        except (ValueError, SyntaxError):
            pass
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]
        return [self._clean_name(item) for item in cleaned.split(",") if item.strip()]

    def _parse_columns(self, text: str) -> list[str]:
        cleaned = text.strip()
        if cleaned.startswith("["):
            return self._parse_list(cleaned)
        return [self._clean_name(item) for item in cleaned.split(",") if item.strip()]

    def _compile_table_expression(self, expression: str, table: str) -> str:
        tokens = self._split_expression(expression)
        compiled: list[str] = []
        for token in tokens:
            if self._is_operator_or_literal(token):
                compiled.append(token)
            else:
                compiled.append(f"{table}[{self._clean_name(token)!r}]")
        py_expr = " ".join(compiled)
        try:
            ast.parse(py_expr, mode="eval")
        except SyntaxError as exc:
            raise DSLParseError(f"新增列表达式不完整或语法错误：{expression}") from exc
        return py_expr

    def _split_expression(self, expression: str) -> list[str]:
        token_re = re.compile(
            r'''
            \s*
            (
                "(?:\\.|[^"\\])*"
                | '(?:\\.|[^'\\])*'
                | -?\d+(?:\.\d+)?
                | [+\-*/()]
                | [A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*
            )
            ''',
            re.VERBOSE,
        )
        tokens: list[str] = []
        position = 0
        while position < len(expression):
            match = token_re.match(expression, position)
            if not match:
                bad = expression[position]
                raise DSLParseError(f"新增列表达式包含不支持的字符：{bad!r}，位置 {position + 1}")
            tokens.append(match.group(1))
            position = match.end()
        if not tokens:
            raise DSLParseError("新增列表达式为空")
        return tokens

    def _is_operator_or_literal(self, token: str) -> bool:
        return bool(
            token in {"+", "-", "*", "/", "(", ")"}
            or re.fullmatch(r'-?\d+(?:\.\d+)?', token)
            or (len(token) >= 2 and token[0] in {'"', "'"} and token[-1] == token[0])
        )

    def _identifier(self, text: str, kind: str = "变量名") -> str:
        cleaned = text.strip()
        if not cleaned.isidentifier() or keyword.iskeyword(cleaned):
            raise DSLParseError(f"{kind}需要是合法的 Python 标识符，例如 订单 或 matrix_a：{text}")
        return cleaned

    def _clean_name(self, text: str) -> str:
        cleaned = text.strip()
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            return str(ast.literal_eval(cleaned))
        return cleaned

    def _strip_comment(self, line: str) -> str:
        in_quote: str | None = None
        for index, char in enumerate(line):
            if char in {'"', "'"}:
                in_quote = None if in_quote == char else char if in_quote is None else in_quote
            if in_quote is None and char == "#":
                return line[:index]
        return line


def compile_file(path: Path) -> CompileResult:
    path = path.resolve()
    compiler = ChineseDataCompiler(base_dir=path.parent)
    return compiler.compile(path.read_text(encoding="utf-8"))


def run_code(code: str) -> None:
    namespace: dict[str, object] = {}
    exec(compile(code, "<zhdata>", "exec"), namespace)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中文 pandas + NumPy DSL 转译器")
    parser.add_argument("script", type=Path, help="中文 DSL 脚本，例如 demo.zd")
    parser.add_argument("--emit-python", action="store_true", help="只输出转译后的 Python 代码")
    parser.add_argument("--output-python", type=Path, help="把转译后的 Python 代码写入指定文件")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = compile_file(args.script)
    except DSLParseError as exc:
        print(exc)
        return 2

    if args.output_python:
        args.output_python.write_text(result.code, encoding="utf-8")

    if args.emit_python:
        print(result.code)
        return 0

    run_code(result.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
