"""Web 接口模块（Flask）。

在推荐技术栈（纯 Python + CLI）之上提供的可选 Web 控制层，
满足 SRS 2.3「命令行界面（CLI）…也可通过 API 调用」的接口需求：
    - GET  /             Web 控制台首页（环境状态）
    - GET  /api/health   健康检查（返回环境与依赖版本）
    - POST /api/sql      （规划）执行 SQL 并返回结果/错误/Plan
    - GET  /api/stats    （规划）缓存命中率等运行统计
"""
