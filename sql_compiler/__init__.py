"""SQL 编译器模块（对应 SRS FR-1.1 ~ FR-1.5）。

依据《软件需求规约文档》第 3.2 节实现编译流水线：

    lex(sql) -> Token[]     词法分析（FR-1.1）
    parse(tokens) -> AST    语法分析（FR-1.2）
    analyze(ast) -> AST     语义分析（FR-1.3）
    plan(ast) -> Plan       执行计划生成（FR-1.4）
    pipeline(sql)           完整流水线输出 Token/AST/Plan（FR-1.5）

模块边界：
    lexer.py     词法分析器（手写递归扫描）
    parser.py    语法分析器（递归下降）
    semantic.py  语义分析器（名字解析 + 类型检查）
    planner.py   逻辑执行计划生成器
    catalog.py   模式目录（编译期 Catalog 接口）
"""
