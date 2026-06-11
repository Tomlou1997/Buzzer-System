import ast, sys, os
os.chdir(r"C:\Users\U0063\Desktop\抢答软件")
files = ['server.py', 'client.py']
imports = set()
for f in files:
    with open(f, 'r', encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
print("=== Python标准库（无需安装）===")
third_party = []
for m in sorted(imports):
    if m in sys.builtin_module_names:
        print(f"  {m}")
    else:
        try:
            __import__(m)
            print(f"  {m} (已安装)")
        except:
            third_party.append(m)
print()
print("=== 需要额外安装 ===")
if third_party:
    for m in third_party:
        print(f"  pip install {m}")
else:
    print("  无需安装任何额外库，纯Python标准库即可运行！")
