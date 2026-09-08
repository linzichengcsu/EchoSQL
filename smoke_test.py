# smoke_test.py
# 依据《推荐技术栈安装指导文档》6.1 节：快速冒烟测试，验证基本运行环境。
import sys


def main():
    print("Python version:", sys.version.split()[0])
    print("Smoke test OK")


if __name__ == "__main__":
    main()
