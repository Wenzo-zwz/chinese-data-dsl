from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from zhdata import ChineseDataCompiler, DSLParseError, compile_file, run_code


class ChineseDataCompilerTests(unittest.TestCase):
    def compile_source(self, source: str) -> str:
        return ChineseDataCompiler(base_dir=ROOT).compile(source).code

    def test_pandas_example_runs_and_writes_expected_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            shutil.copy2(ROOT / "references" / "example_pandas.zd", tmp / "example_pandas.zd")
            shutil.copy2(ROOT / "references" / "demo_data.csv", tmp / "demo_data.csv")

            result = compile_file(tmp / "example_pandas.zd")
            run_code(result.code)

            output = tmp / "city_sales.csv"
            self.assertTrue(output.exists())
            data = pd.read_csv(output)
            self.assertEqual(list(data.columns), ["城市", "总销售额"])
            self.assertEqual(data.iloc[0].to_dict(), {"城市": "上海", "总销售额": 10000})

    def test_numpy_example_runs_and_writes_expected_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            shutil.copy2(ROOT / "references" / "example_numpy.zd", tmp / "example_numpy.zd")

            result = compile_file(tmp / "example_numpy.zd")
            run_code(result.code)

            matrix = np.load(tmp / "matrix.npy")
            np.testing.assert_array_equal(matrix, np.array([[5, 11], [11, 25]]))

    def test_contains_uses_literal_matching(self) -> None:
        code = self.compile_source(
            '\n'.join(
                [
                    '读取CSV "demo.csv" 为 订单',
                    '筛选 品类 包含 "."',
                ]
            )
        )

        self.assertIn("regex=False", code)

    def test_invalid_identifier_fails_before_python_generation(self) -> None:
        with self.assertRaisesRegex(DSLParseError, "表名需要是合法的 Python 标识符"):
            self.compile_source('读取CSV "demo.csv" 为 123订单')

    def test_unknown_expression_character_fails(self) -> None:
        with self.assertRaisesRegex(DSLParseError, "新增列表达式包含不支持的字符"):
            self.compile_source(
                '\n'.join(
                    [
                        '读取CSV "demo.csv" 为 订单',
                        "新增列 异常 = 销售额 @ 数量",
                    ]
                )
            )


if __name__ == "__main__":
    unittest.main()
